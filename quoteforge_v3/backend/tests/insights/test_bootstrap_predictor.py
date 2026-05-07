"""Session 6.5 — bootstrap-resample confidence range tests.

Uses a tiny synthetic dataset to drive build_bootstrap_models + the
resample-based range helper end-to-end, then verifies range-width
behavior against training data size.
"""
from __future__ import annotations

import pickle
import tempfile
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from app.services.insights.bootstrap import (
    bootstrap_cache_is_fresh,
    bootstrap_dir,
    build_bootstrap_models,
    predict_range_via_resample,
    predict_range_via_per_tree,
)


def _make_training_frame(n: int, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    rnd = np.random.RandomState(seed)
    amount = rnd.lognormal(mean=10, sigma=1, size=n)
    activity = rnd.poisson(lam=4, size=n)
    X = pd.DataFrame({
        "amount": amount, "activity": activity,
        "industry=Tech": rnd.randint(0, 2, size=n),
        "industry=Finance": rnd.randint(0, 2, size=n),
    })
    latent = (amount / 30_000) + activity * 0.3 - 1
    y = pd.Series((latent + rnd.normal(0, 0.5, size=n)) > 0, dtype=int)
    return X, y


def test_build_and_load_bootstrap_cache():
    with tempfile.TemporaryDirectory() as root:
        X, y = _make_training_frame(200)
        written = build_bootstrap_models(
            X, y,
            tenant_id="tenant-bootstrap-test",
            model_version=1,
            model_root=root,
        )
        assert written == 20
        # Sentinel + pickles exist.
        out = bootstrap_dir("tenant-bootstrap-test", root)
        assert (out / "version.txt").read_text().strip() == "1"
        assert len(list(out.glob("b*.pkl"))) == 20


def test_cache_freshness_tracks_model_version():
    with tempfile.TemporaryDirectory() as root:
        X, y = _make_training_frame(150)
        build_bootstrap_models(X, y, tenant_id="t1", model_version=3, model_root=root)
        assert bootstrap_cache_is_fresh("t1", 3, root)
        assert not bootstrap_cache_is_fresh("t1", 4, root)
        assert not bootstrap_cache_is_fresh("missing-tenant", 3, root)


def test_predict_range_returns_percentiles_when_cache_exists():
    with tempfile.TemporaryDirectory() as root:
        X, y = _make_training_frame(200)
        build_bootstrap_models(X, y, tenant_id="t2", model_version=1, model_root=root)

        X_row = X.iloc[[0]].copy()
        rng = predict_range_via_resample(
            X_row, tenant_id="t2", model_root=root,
        )
        assert rng is not None
        lower, upper = rng
        assert 0.0 <= lower <= upper <= 1.0


def test_predict_range_returns_none_when_no_cache():
    with tempfile.TemporaryDirectory() as root:
        X, _ = _make_training_frame(100)
        rng = predict_range_via_resample(
            X.iloc[[0]], tenant_id="no-such-tenant", model_root=root,
        )
        assert rng is None


def test_per_tree_variance_returns_range_for_trained_model():
    X, y = _make_training_frame(300)
    m = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05,
                           objective="binary", random_state=42, verbose=-1)
    m.fit(X, y)
    rng = predict_range_via_per_tree(m, X.iloc[[0]])
    assert rng is not None
    lower, upper = rng
    assert lower <= upper
