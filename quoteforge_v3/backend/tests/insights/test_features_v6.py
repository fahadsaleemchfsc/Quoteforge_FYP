"""Tests for Phase 2 feature additions:
- days_in_current_stage (with stage_change fallback to age_days)
- activity_velocity (handles age_days=0 without ZeroDivisionError)
- expected_close_distance (negative values for past close dates)
- cross-object: contact_activity_count, contact_days_since_last_activity,
  account_activity_count_365d, account_engagement_diversity,
  days_since_account_last_activity, contact_count_on_account
- weak-signal: product_tier, sales_region (from country), quarter (from date)
"""
from __future__ import annotations

from datetime import date

from app.services.insights.features import (
    CATEGORICAL_BASE_COLS,
    MappingBundle,
    build_feature_frame,
    one_hot_and_align,
)


def _mapping(**overrides) -> MappingBundle:
    base = dict(
        amount_field="Amount", stage_field="StageName",
        close_date_field="CloseDate", created_date_field="CreatedDate",
        is_closed_field="IsClosed", is_won_field="IsWon",
        industry_field="Account.Industry", lead_source_field="LeadSource",
        owner_field="OwnerId", record_type_field=None,
        custom_fields=[],
    )
    base.update(overrides)
    return MappingBundle(**base)


def _base_opp(**overrides) -> dict:
    o = {
        "Id": "006V6_01",
        "Amount": 50_000,
        "StageName": "Proposal",
        "CloseDate": "2026-05-23",
        "CreatedDate": "2026-03-24",
        "IsWon": False,
        "Account": {"Industry": "Technology", "BillingCountry": "United States"},
        "LeadSource": "Referral",
        "OwnerId": "005001",
    }
    o.update(overrides)
    return o


def test_days_to_close_is_no_longer_a_column():
    """Phase 2 Step 2.1 — days_to_close was removed from the feature set
    because of training-vs-inference distribution mismatch."""
    df = build_feature_frame([_base_opp()], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert "days_to_close" not in df.columns


def test_expected_close_distance_matches_future_close():
    df = build_feature_frame([_base_opp()], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["expected_close_distance"] == 30


def test_expected_close_distance_is_negative_for_overdue_deals():
    opp = _base_opp(CloseDate="2026-03-15")   # 39 days in the past
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["expected_close_distance"] < 0


def test_activity_velocity_handles_zero_age_without_dividing_by_zero():
    opp = _base_opp(CreatedDate="2026-04-23")   # age_days=0
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    # activity_velocity = 0 / max(0, 1) = 0; must not raise
    assert df.iloc[0]["activity_velocity"] == 0
    assert df.iloc[0]["age_days"] == 0


def test_activity_velocity_scales_with_activity_count():
    opp = _base_opp()   # age_days = 30
    acts = {opp["Id"]: [{"ActivityDate": "2026-04-20"}] * 6}
    df = build_feature_frame([opp], acts, _mapping(),
                             reference_date=date(2026, 4, 23))
    # 6 activities over 30 days = 0.2
    assert abs(df.iloc[0]["activity_velocity"] - 6 / 30) < 1e-6


def test_days_in_current_stage_falls_back_to_age_days_without_mapping():
    """No stage_change_date_field mapped → should fall back to age_days."""
    df = build_feature_frame([_base_opp()], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["days_in_current_stage"] == df.iloc[0]["age_days"]


def test_days_in_current_stage_honors_mapped_field():
    opp = _base_opp(LastStageChange="2026-04-08")
    m = _mapping(stage_change_date_field="LastStageChange")
    df = build_feature_frame([opp], {}, m, reference_date=date(2026, 4, 23))
    assert df.iloc[0]["days_in_current_stage"] == 15


def test_cross_object_contact_activity_features_extract_correctly():
    opp = _base_opp(_contact_activities=[
        {"ActivityDate": "2026-04-01", "Type": "Call"},
        {"ActivityDate": "2026-04-15", "Type": "Email"},
        {"ActivityDate": "2026-04-20", "Type": "Meeting"},
    ])
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["contact_activity_count"] == 3
    assert df.iloc[0]["contact_days_since_last_activity"] == 3   # most recent 04-20


def test_cross_object_account_engagement_diversity():
    opp = _base_opp(
        _account_activities=[
            {"ActivityDate": "2026-04-01", "Type": "Call"},
            {"ActivityDate": "2026-04-10", "Type": "Email"},
            {"ActivityDate": "2026-04-15", "Type": "Call"},
            {"ActivityDate": "2026-04-18", "Type": "Demo"},
        ],
        _contact_count_on_account=4,
    )
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["account_activity_count_365d"] == 4
    assert df.iloc[0]["account_engagement_diversity"] == 3   # Call, Email, Demo
    assert df.iloc[0]["contact_count_on_account"] == 4


def test_missing_cross_object_fields_default_cleanly():
    """No Contact, no Account activities — features should be 0, not raise."""
    df = build_feature_frame([_base_opp()], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    row = df.iloc[0]
    assert row["contact_activity_count"] == 0
    assert row["account_activity_count_365d"] == 0
    assert row["account_engagement_diversity"] == 0
    assert row["contact_count_on_account"] == 0


def test_sales_region_derives_from_billing_country():
    """Live SF path: sales_region falls back to Account.BillingCountry mapping."""
    opp = _base_opp()
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["sales_region"] == "NA"


def test_sales_region_uses_explicit_training_value_when_present():
    """Training path: SalesRegion column takes precedence over country lookup."""
    opp = _base_opp(SalesRegion="APAC",
                    Account={"Industry": "Tech", "BillingCountry": "Japan"})
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["sales_region"] == "APAC"


def test_quarter_derives_from_close_date():
    opp = _base_opp(CloseDate="2026-08-15")
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["quarter"] == "Q3"


def test_product_tier_falls_back_to_unknown_without_mapping():
    df = build_feature_frame([_base_opp()], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["product_tier"] == "UNKNOWN"


def test_product_tier_uses_training_data_key():
    opp = _base_opp(ProductTier="Enterprise")
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    assert df.iloc[0]["product_tier"] == "Enterprise"


def test_one_hot_alignment_includes_all_v6_categoricals():
    """CATEGORICAL_BASE_COLS must include the three weak-signal adds."""
    for col in ("industry", "lead_source", "record_type", "owner_id",
                "product_tier", "sales_region", "quarter"):
        assert col in CATEGORICAL_BASE_COLS, f"missing {col}"

    opp = _base_opp(ProductTier="Standard", SalesRegion="EMEA", Quarter="Q2")
    df = build_feature_frame([opp], {}, _mapping(),
                             reference_date=date(2026, 4, 23))
    X = one_hot_and_align(df, categorical_cols=CATEGORICAL_BASE_COLS,
                          custom_categorical_cols=[])
    # One-hot should produce prefix=value columns for each categorical input.
    for expected in ("product_tier=Standard", "sales_region=EMEA", "quarter=Q2"):
        assert expected in X.columns, f"missing one-hot column {expected}"
