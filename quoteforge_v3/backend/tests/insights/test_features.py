"""Unit tests for feature-engineering — exercises the pipeline on a handful
of hand-crafted Opp records + activities.

Run:
    cd backend && ./venv/bin/pytest tests/insights/test_features.py -v
"""
from __future__ import annotations

from datetime import date

from app.services.insights.features import (
    CATEGORICAL_BASE_COLS,
    MappingBundle,
    build_feature_frame,
    one_hot_and_align,
    targets_from_records,
)


def _mapping() -> MappingBundle:
    return MappingBundle(
        amount_field="Amount",
        stage_field="StageName",
        close_date_field="CloseDate",
        created_date_field="CreatedDate",
        is_closed_field="IsClosed",
        is_won_field="IsWon",
        industry_field="Account.Industry",
        lead_source_field="LeadSource",
        owner_field="OwnerId",
        record_type_field="RecordTypeId",
        custom_fields=[],
    )


def test_build_feature_frame_computes_expected_close_distance_and_age():
    # Phase 2: `days_to_close` was renamed to `expected_close_distance`.
    ref = date(2026, 4, 23)
    opps = [{
        "Id": "006A",
        "Amount": 50_000,
        "StageName": "Proposal",
        "CloseDate": "2026-05-23",           # 30 days out
        "CreatedDate": "2026-03-24",         # 30 days old
        "IsClosed": False,
        "IsWon": False,
        "Account": {"Industry": "Technology"},
        "LeadSource": "Referral",
        "OwnerId": "005001",
        "RecordTypeId": None,
    }]
    df = build_feature_frame(opps, {"006A": []}, _mapping(), reference_date=ref)
    row = df.iloc[0]
    assert row["amount"] == 50_000
    assert row["expected_close_distance"] == 30
    assert row["age_days"] == 30
    assert row["industry"] == "Technology"
    assert row["lead_source"] == "Referral"


def test_build_feature_frame_handles_missing_optional_fields():
    ref = date(2026, 4, 23)
    opps = [{
        "Id": "006B",
        "Amount": 0,
        "CloseDate": None,
        "CreatedDate": None,
        "IsWon": False,
    }]
    df = build_feature_frame(opps, {}, _mapping(), reference_date=ref)
    row = df.iloc[0]
    assert row["amount"] == 0
    # Missing dates → 0 rather than raising.
    assert row["expected_close_distance"] == 0
    assert row["age_days"] == 0
    assert row["industry"] == "UNKNOWN"


def test_activity_count_and_recency_computed_from_related_records():
    ref = date(2026, 4, 23)
    opps = [{
        "Id": "006C",
        "Amount": 10_000,
        "CloseDate": "2026-06-01",
        "CreatedDate": "2026-01-01",
        "IsWon": False,
        "Account": {"Industry": "Finance"},
    }]
    activities = {
        "006C": [
            {"ActivityDate": "2026-04-01"},   # 22 days ago
            {"ActivityDate": "2026-03-15"},
            {"ActivityDate": "2026-04-20"},   # most recent, 3 days ago
        ],
    }
    df = build_feature_frame(opps, activities, _mapping(), reference_date=ref)
    row = df.iloc[0]
    assert row["activity_count"] == 3
    assert row["days_since_last_activity"] == 3


def test_one_hot_and_align_creates_stable_columns():
    ref = date(2026, 4, 23)
    opps = [
        {"Id": f"006{i}", "Amount": 1000 + i, "CloseDate": "2026-05-23",
         "CreatedDate": "2026-03-24", "IsWon": False,
         "Account": {"Industry": ind}, "LeadSource": "Web", "OwnerId": "005001"}
        for i, ind in enumerate(["Technology", "Finance", "Technology"])
    ]
    df = build_feature_frame(opps, {}, _mapping(), reference_date=ref)
    X = one_hot_and_align(df, categorical_cols=CATEGORICAL_BASE_COLS,
                          custom_categorical_cols=[])

    assert "industry=Technology" in X.columns
    assert "industry=Finance" in X.columns
    # numeric columns passed through
    assert "amount" in X.columns
    assert "opp_id" not in X.columns  # dropped


def test_one_hot_and_align_respects_reference_columns_for_prediction():
    """At prediction time, reference_columns pins the output to the training
    feature set — unseen categories get dropped, missing categories get zeros."""
    ref = date(2026, 4, 23)
    train_opps = [
        {"Id": f"006T{i}", "Amount": 1000, "CloseDate": "2026-05-23",
         "CreatedDate": "2026-03-24", "IsWon": False,
         "Account": {"Industry": ind}, "LeadSource": "Web", "OwnerId": "005001"}
        for i, ind in enumerate(["Technology", "Finance"])
    ]
    train_df = build_feature_frame(train_opps, {}, _mapping(), reference_date=ref)
    train_X = one_hot_and_align(train_df, categorical_cols=CATEGORICAL_BASE_COLS,
                                custom_categorical_cols=[])
    training_columns = list(train_X.columns)

    # Prediction-time Opp has industry=Retail (unseen) — should not create a
    # new column, output must match training_columns exactly.
    test_opps = [{"Id": "006P", "Amount": 1000, "CloseDate": "2026-05-23",
                  "CreatedDate": "2026-03-24", "IsWon": False,
                  "Account": {"Industry": "Retail"}, "LeadSource": "Web",
                  "OwnerId": "005001"}]
    test_df = build_feature_frame(test_opps, {}, _mapping(), reference_date=ref)
    test_X = one_hot_and_align(
        test_df, categorical_cols=CATEGORICAL_BASE_COLS,
        custom_categorical_cols=[],
        reference_columns=training_columns,
    )
    assert list(test_X.columns) == training_columns


def test_targets_from_records_emits_binary_labels():
    y = targets_from_records(
        [{"IsWon": True}, {"IsWon": False}, {"IsWon": True}], _mapping(),
    )
    assert list(y) == [1, 0, 1]


def test_custom_numeric_and_boolean_fields_flow_into_frame():
    ref = date(2026, 4, 23)
    mapping = _mapping()
    mapping.custom_fields = [
        {"sf_field": "Priority__c", "feature_name": "priority", "type": "numeric"},
        {"sf_field": "Urgent__c",   "feature_name": "urgent",   "type": "boolean"},
    ]
    opps = [{"Id": "006X", "Amount": 1000, "CloseDate": "2026-05-23",
             "CreatedDate": "2026-03-24", "IsWon": False,
             "Account": {"Industry": "Technology"}, "LeadSource": "Web",
             "OwnerId": "005001",
             "Priority__c": "3", "Urgent__c": True}]
    df = build_feature_frame(opps, {}, mapping, reference_date=ref)
    row = df.iloc[0]
    assert row["priority"] == 3.0
    assert row["urgent"] == 1
