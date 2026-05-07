"""Data-quality guardrails around the trainer: insufficient-data and
single-class-only cases must raise the right error with actionable messages.

These don't call train_model_for_tenant end-to-end — they exercise the
internal `_enforce_minimum` helper directly. That keeps the test fast and
independent of DB + SF.
"""
from __future__ import annotations

import pytest

from app.services.insights.features import MappingBundle
from app.services.insights.trainer import (
    InsufficientDataError,
    UnsupportedDataError,
    _enforce_minimum,
)


def _mapping() -> MappingBundle:
    return MappingBundle(
        amount_field="Amount", stage_field="StageName",
        close_date_field="CloseDate", created_date_field="CreatedDate",
        is_closed_field="IsClosed", is_won_field="IsWon",
        industry_field=None, lead_source_field=None,
        owner_field=None, record_type_field=None,
        custom_fields=[],
    )


def _rows(wins: int, losses: int) -> list[dict]:
    return (
        [{"IsWon": True} for _ in range(wins)]
        + [{"IsWon": False} for _ in range(losses)]
    )


def test_enforce_minimum_hard_floor_is_100_with_friendly_message():
    # Session 6.5: raised hard floor from 50 to 100 with a rep-facing message.
    with pytest.raises(InsufficientDataError) as exc:
        _enforce_minimum(_rows(40, 40), _mapping())
    msg = str(exc.value)
    assert "100" in msg
    assert "80" in msg  # echoes the actual count back to the reader


def test_enforce_minimum_class_imbalance_above_floor():
    # 100+ rows but one side < 10 → still rejected.
    with pytest.raises(InsufficientDataError) as exc:
        _enforce_minimum(_rows(5, 100), _mapping())
    assert "imbalance" in str(exc.value).lower()


def test_single_class_dataset_raises_unsupported():
    # 120 rows, all won — unsupported (need both classes).
    with pytest.raises(UnsupportedDataError):
        _enforce_minimum(_rows(120, 0), _mapping())


def test_enforce_minimum_passes_on_balanced_sufficient_data():
    # 100 rows, 50 each — just above hard floor, balanced. Must not raise.
    _enforce_minimum(_rows(50, 50), _mapping())


def test_classify_data_quality_tier_buckets():
    from app.services.insights.trainer import classify_data_quality_tier
    assert classify_data_quality_tier(50) == "insufficient"
    assert classify_data_quality_tier(100) == "early_stage"
    assert classify_data_quality_tier(299) == "early_stage"
    assert classify_data_quality_tier(300) == "standard"
    assert classify_data_quality_tier(999) == "standard"
    assert classify_data_quality_tier(1000) == "mature"
    assert classify_data_quality_tier(5000) == "mature"
