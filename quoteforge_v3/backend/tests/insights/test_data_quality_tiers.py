"""Session 6.5 — hard-floor + four-tier data-quality classification."""
from __future__ import annotations

import pytest

from app.services.insights.trainer import (
    MIN_DEALS_HARD_FLOOR,
    MIN_DEALS_EARLY_STAGE,
    MIN_DEALS_STANDARD,
    InsufficientDataError,
    classify_data_quality_tier,
)


def test_hard_floor_is_100_not_50():
    assert MIN_DEALS_HARD_FLOOR == 100


def test_tier_boundaries():
    assert classify_data_quality_tier(0) == "insufficient"
    assert classify_data_quality_tier(MIN_DEALS_HARD_FLOOR - 1) == "insufficient"
    assert classify_data_quality_tier(MIN_DEALS_HARD_FLOOR) == "early_stage"
    assert classify_data_quality_tier(MIN_DEALS_EARLY_STAGE - 1) == "early_stage"
    assert classify_data_quality_tier(MIN_DEALS_EARLY_STAGE) == "standard"
    assert classify_data_quality_tier(MIN_DEALS_STANDARD - 1) == "standard"
    assert classify_data_quality_tier(MIN_DEALS_STANDARD) == "mature"
    assert classify_data_quality_tier(50_000) == "mature"


def test_enforce_minimum_rejects_below_floor_with_friendly_message():
    from app.services.insights.trainer import _enforce_minimum
    from app.services.insights.features import MappingBundle
    mapping = MappingBundle(
        amount_field="Amount", stage_field="StageName",
        close_date_field="CloseDate", created_date_field="CreatedDate",
        is_closed_field="IsClosed", is_won_field="IsWon",
        industry_field=None, lead_source_field=None,
        owner_field=None, record_type_field=None, custom_fields=[],
    )
    opps = ([{"IsWon": True} for _ in range(25)]
            + [{"IsWon": False} for _ in range(25)])
    with pytest.raises(InsufficientDataError) as exc:
        _enforce_minimum(opps, mapping)
    msg = str(exc.value)
    # Friendly message mentions both the current count + the threshold.
    assert "50" in msg   # current count
    assert "100" in msg  # threshold


def test_tiers_are_monotone_increasing():
    """A tenant that adds deals only moves up the tier ladder (or stays put),
    never down."""
    order = ["insufficient", "early_stage", "standard", "mature"]
    prev_idx = -1
    for n in (50, 99, 100, 150, 299, 300, 500, 999, 1000, 5000):
        tier = classify_data_quality_tier(n)
        idx = order.index(tier)
        assert idx >= prev_idx, f"regressed at n={n}: {tier}"
        prev_idx = idx
