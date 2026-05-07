"""
Bootstrap predictor — confidence ranges for Deal Insights win probabilities.

Two strategies based on data-quality tier:

  early_stage (100-299 closed deals):
      Resample the training frame 20 times with replacement, train 20
      lightweight LightGBM models (n_estimators=50), predict with each,
      return (p10, mean, p90). Legitimate model-variance signal — honest
      about how uncertain a model trained on limited data really is.

  standard / mature (300+ deals):
      Per-tree variance across the main model's 200 boosters. Each tree
      casts a vote; variance of those votes proxies prediction confidence.
      No extra training cost.

Bootstrap pickles live at:
    storage/insights_models/{tenant_id}/bootstrap/b{i}.pkl

They regenerate when the main model version bumps (detected via a
`version` sentinel file in the same directory).
"""
from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.utils import resample

logger = logging.getLogger(__name__)

N_BOOTSTRAP_MODELS = 20
BOOTSTRAP_N_ESTIMATORS = 50   # lighter than main model's 200
LOWER_PERCENTILE = 10
UPPER_PERCENTILE = 90


# ─── Build / cache ──────────────────────────────────────────────────

def bootstrap_dir(tenant_id: str, model_root: str) -> Path:
    return Path(model_root) / tenant_id / "bootstrap"


def _version_sentinel(tenant_id: str, model_root: str) -> Path:
    return bootstrap_dir(tenant_id, model_root) / "version.txt"


def bootstrap_cache_is_fresh(
    tenant_id: str, model_version: int, model_root: str,
) -> bool:
    sentinel = _version_sentinel(tenant_id, model_root)
    if not sentinel.exists():
        return False
    try:
        return sentinel.read_text().strip() == str(model_version)
    except Exception:
        return False


def build_bootstrap_models(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    tenant_id: str,
    model_version: int,
    model_root: str,
    seed_base: int = 2026,
) -> int:
    """Train + persist N_BOOTSTRAP_MODELS. Returns count written."""
    out_dir = bootstrap_dir(tenant_id, model_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear any stale pickles from the previous version.
    for old in out_dir.glob("b*.pkl"):
        try:
            old.unlink()
        except OSError:
            pass

    written = 0
    for i in range(N_BOOTSTRAP_MODELS):
        X_res, y_res = resample(
            X, y, replace=True, n_samples=len(X), random_state=seed_base + i,
        )
        model = lgb.LGBMClassifier(
            n_estimators=BOOTSTRAP_N_ESTIMATORS,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=15,
            min_data_in_leaf=5,
            objective="binary",
            random_state=seed_base + i,
            verbose=-1,
        )
        model.fit(X_res, y_res)
        with open(out_dir / f"b{i}.pkl", "wb") as f:
            pickle.dump({"model": model, "columns": list(X.columns)}, f)
        written += 1

    _version_sentinel(tenant_id, model_root).write_text(str(model_version))
    logger.info(
        "insights.bootstrap: tenant=%s version=%d wrote %d models",
        tenant_id, model_version, written,
    )
    return written


# ─── Runtime prediction ─────────────────────────────────────────────

def predict_range_via_resample(
    X_row: pd.DataFrame,
    *,
    tenant_id: str,
    model_root: str,
) -> tuple[float, float] | None:
    """Average over N_BOOTSTRAP_MODELS resample-trained models.

    Returns (lower, upper) percentiles, or None if the cache isn't present.
    Caller decides whether to fall through to per-tree variance or just
    return the point estimate without a range.
    """
    out_dir = bootstrap_dir(tenant_id, model_root)
    pickles = sorted(out_dir.glob("b*.pkl"))
    if not pickles:
        return None

    probs: list[float] = []
    for pkl in pickles:
        try:
            with open(pkl, "rb") as f:
                bundle = pickle.load(f)
        except Exception as e:
            logger.info("bootstrap load %s failed (%s)", pkl.name, e)
            continue
        cols = bundle["columns"]
        # Align inference row to this bootstrap model's columns.
        aligned = X_row.reindex(columns=cols, fill_value=0)
        try:
            p = float(bundle["model"].predict_proba(aligned)[:, 1][0])
            probs.append(p)
        except Exception as e:
            logger.info("bootstrap predict %s failed (%s)", pkl.name, e)

    if len(probs) < 3:
        return None
    arr = np.asarray(probs)
    return float(np.percentile(arr, LOWER_PERCENTILE)), \
           float(np.percentile(arr, UPPER_PERCENTILE))


def predict_range_via_per_tree(
    model: Any, X_row: pd.DataFrame,
) -> tuple[float, float] | None:
    """Cheap per-tree variance proxy for standard/mature tiers. Uses
    `pred_leaf=True` to get per-tree leaf indices, then evaluates each tree's
    contribution by splitting n_estimators into quintiles and predicting with
    increasingly large truncations. A hack but bounded and deterministic.

    Returns (lower, upper) or None if LightGBM internals aren't reachable.
    """
    try:
        booster = model.booster_ if hasattr(model, "booster_") else model
        total_rounds = booster.num_trees() if hasattr(booster, "num_trees") else \
            getattr(model, "n_estimators", 200)
    except Exception:
        return None

    if total_rounds < 10:
        return None

    # Predict with increasing number of trees — early-stop snapshots at 25%,
    # 50%, 75%, 100% give us a cheap variance proxy.
    snapshots: list[float] = []
    for fraction in (0.25, 0.5, 0.75, 1.0):
        try:
            raw = booster.predict(X_row.values, num_iteration=int(total_rounds * fraction))
            # Binary classifier booster returns probabilities directly.
            p = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
            snapshots.append(p)
        except Exception:
            continue

    if len(snapshots) < 3:
        return None
    arr = np.asarray(snapshots)
    return float(arr.min()), float(arr.max())
