"""End-to-end smoke test for the train → pickle → predict pipeline.

Trains a real LightGBM on a tiny synthetic dataset, serializes + reloads it,
and checks that predictions land in [0, 1] and produce coherent SHAP drivers.
This catches regressions in feature alignment + pickle compatibility that
the unit tests above would miss.
"""
from __future__ import annotations

import pickle
import tempfile
from pathlib import Path

import lightgbm as lgb
import numpy as np

from app.services.insights.features import (
    CATEGORICAL_BASE_COLS,
    MappingBundle,
    build_feature_frame,
    one_hot_and_align,
    targets_from_records,
)
from app.services.insights.predictor import _compute_drivers


def _mapping() -> MappingBundle:
    return MappingBundle(
        amount_field="Amount", stage_field="StageName",
        close_date_field="CloseDate", created_date_field="CreatedDate",
        is_closed_field="IsClosed", is_won_field="IsWon",
        industry_field="Account.Industry", lead_source_field="LeadSource",
        owner_field="OwnerId", record_type_field=None,
        custom_fields=[],
    )


def _rows(n: int, win_bias: float) -> list[dict]:
    from datetime import date, timedelta
    today = date(2026, 4, 23)
    rows = []
    for i in range(n):
        amount = 50_000 + (i * 1000 if i % 2 == 0 else -i * 500)
        is_won = (amount > 60_000) if (i % 3 != 0) else (amount < 30_000)
        rows.append({
            "Id": f"006T{i:03d}",
            "Amount": amount,
            "StageName": "Closed Won" if is_won else "Closed Lost",
            "CloseDate": (today - timedelta(days=i)).isoformat(),
            "CreatedDate": (today - timedelta(days=60 + i)).isoformat(),
            "IsClosed": True,
            "IsWon": is_won,
            "Account": {"Industry": "Technology" if i % 2 == 0 else "Retail"},
            "LeadSource": "Referral" if i % 3 == 0 else "Web",
            "OwnerId": f"005{(i % 3) + 1:03d}",
        })
    return rows


def test_train_pickle_predict_roundtrip():
    """Train → save pickle → load pickle → predict. Verifies the bundle
    contents match what the predictor reads."""
    opps = _rows(80, 0.5)
    df = build_feature_frame(opps, {}, _mapping())
    y = targets_from_records(opps, _mapping())
    X = one_hot_and_align(df, categorical_cols=CATEGORICAL_BASE_COLS,
                          custom_categorical_cols=[])

    model = lgb.LGBMClassifier(
        n_estimators=30, learning_rate=0.1, max_depth=4,
        min_data_in_leaf=3, objective="binary", verbose=-1, random_state=42,
    )
    model.fit(X, y)

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "v1.pkl"
        with open(path, "wb") as f:
            pickle.dump({
                "model": model,
                "feature_columns": list(X.columns),
                "categorical_cols": CATEGORICAL_BASE_COLS,
                "custom_categorical_cols": [],
                "trained_at": "2026-04-23T00:00:00+00:00",
            }, f)
        with open(path, "rb") as f:
            bundle = pickle.load(f)

    assert bundle["model"] is not None
    assert list(bundle["feature_columns"]) == list(X.columns)

    # Predict on a held-out synthetic Opp with the reloaded model, verify
    # feature alignment.
    new_opp = _rows(1, 0.5)[:1]
    new_df = build_feature_frame(new_opp, {}, _mapping())
    new_X = one_hot_and_align(
        new_df, categorical_cols=CATEGORICAL_BASE_COLS,
        custom_categorical_cols=[],
        reference_columns=bundle["feature_columns"],
    )
    prob = bundle["model"].predict_proba(new_X)[:, 1][0]
    assert 0.0 <= prob <= 1.0


def test_compute_drivers_returns_signed_top_k():
    opps = _rows(80, 0.5)
    df = build_feature_frame(opps, {}, _mapping())
    y = targets_from_records(opps, _mapping())
    X = one_hot_and_align(df, categorical_cols=CATEGORICAL_BASE_COLS,
                          custom_categorical_cols=[])
    model = lgb.LGBMClassifier(
        n_estimators=30, learning_rate=0.1, max_depth=4,
        min_data_in_leaf=3, objective="binary", verbose=-1, random_state=42,
    )
    model.fit(X, y)

    drivers = _compute_drivers(model, X.iloc[:1], list(X.columns))
    # At most 3 positive + 3 negative.
    assert 0 < len(drivers) <= 6
    for d in drivers:
        assert "feature" in d and "shap_value" in d and "direction" in d
        assert d["direction"] in {"positive", "negative"}
