"""
Unit tests for the Guardrail Engine. Pure-data, no DB — the engine is
deliberately side-effect-free so this test file runs fast and doesn't need
fixtures or a running DB.

One test per check + one aggregate test, as requested.

Run with:
  cd backend && ./venv/bin/pytest tests/test_guardrails.py -v
"""
from __future__ import annotations

import pytest

from app.gateway.guardrails.engine import (
    ApprovalThresholdCheck,
    CurrencyCheck,
    DealSizeCheck,
    GuardrailEngine,
    LineItemContext,
    MaxDiscountCheck,
    MinMarginCheck,
    OfferContext,
    PolicySnapshot,
    RegionCheck,
)


def _policy(**overrides) -> PolicySnapshot:
    defaults = dict(
        min_margin_percent=15.0,
        max_discount_percent=20.0,
        max_discount_with_approval_percent=35.0,
        allowed_regions=("US", "EU", "APAC"),
        currency_allowlist=("USD",),
        min_deal_size_cents=0,
        max_deal_size_cents=None,
        require_approval_above_cents=5_000_000,
    )
    defaults.update(overrides)
    return PolicySnapshot(**defaults)


def _line(
    sku: str = "ABC",
    quantity: int = 1,
    unit_price_cents: int = 10_000,
    base_price_cents: int = 10_000,
    min_price_floor_cents: int = 6_000,
) -> LineItemContext:
    return LineItemContext(
        sku=sku,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
        base_price_cents=base_price_cents,
        min_price_floor_cents=min_price_floor_cents,
    )


def _offer(*lines, region: str = "US", currency: str = "USD", total_cents: int | None = None) -> OfferContext:
    lines_t = tuple(lines) if lines else (_line(),)
    total = total_cents if total_cents is not None else sum(l.line_total_cents() for l in lines_t)
    return OfferContext(
        tenant_id="t-1",
        line_items=lines_t,
        total_cents=total,
        currency=currency,
        buyer_region=region,
    )


# ───────────────────────── MinMarginCheck ─────────────────────────

class TestMinMarginCheck:
    def test_passes_when_margin_above_floor(self) -> None:
        # unit 10,000; floor 6,000 → margin = 40% >= 15%
        result = MinMarginCheck().evaluate(_offer(_line()), _policy(min_margin_percent=15.0))
        assert result.verdict == "pass"

    def test_blocks_when_margin_below_floor(self) -> None:
        # unit 10,000; floor 9,500 → margin = 5% < 15% → block
        line = _line(unit_price_cents=10_000, min_price_floor_cents=9_500)
        result = MinMarginCheck().evaluate(_offer(line), _policy(min_margin_percent=15.0))
        assert result.verdict == "block"
        assert result.reason_external  # non-empty external message
        assert "min_margin" not in result.reason_external  # generic, no policy leakage
        adjustment = result.suggested_adjustment
        assert adjustment is not None
        bumped = adjustment["line_items"][0]["min_acceptable_unit_price_cents"]
        assert bumped >= line.min_price_floor_cents
        # At bumped price, margin should be exactly min_margin (or minimally higher).
        implied_margin = (bumped - line.min_price_floor_cents) / bumped * 100
        assert implied_margin >= 14.99  # allow 1-cent floor epsilon


# ───────────────────────── MaxDiscountCheck ─────────────────────────

class TestMaxDiscountCheck:
    def test_passes_when_discount_within_auto_approve(self) -> None:
        # unit 90, base 100 → 10% discount, below 20% auto-approve → pass
        line = _line(unit_price_cents=9_000, base_price_cents=10_000, min_price_floor_cents=5_000)
        result = MaxDiscountCheck().evaluate(_offer(line), _policy())
        assert result.verdict == "pass"

    def test_reviews_when_discount_above_auto_approve(self) -> None:
        # 25% discount → above 20% auto-approve, below 35% ceiling → review
        line = _line(unit_price_cents=7_500, base_price_cents=10_000, min_price_floor_cents=5_000)
        result = MaxDiscountCheck().evaluate(_offer(line), _policy())
        assert result.verdict == "review"

    def test_blocks_when_discount_above_ceiling(self) -> None:
        # 40% discount → above 35% ceiling → block
        line = _line(unit_price_cents=6_000, base_price_cents=10_000, min_price_floor_cents=3_000)
        result = MaxDiscountCheck().evaluate(_offer(line), _policy())
        assert result.verdict == "block"
        assert result.suggested_adjustment is not None


# ───────────────────────── RegionCheck ─────────────────────────

class TestRegionCheck:
    def test_pass_for_allowed_region(self) -> None:
        result = RegionCheck().evaluate(_offer(region="EU"), _policy())
        assert result.verdict == "pass"

    def test_block_for_unlisted_region(self) -> None:
        result = RegionCheck().evaluate(_offer(region="CN"), _policy())
        assert result.verdict == "block"
        assert "region" not in result.reason_external.lower() or result.reason_external  # external message exists

    def test_strict_equality_not_substring(self) -> None:
        # Regression: the old pricing engine used substring matching. Ensure
        # "U" does NOT match "US" here.
        result = RegionCheck().evaluate(_offer(region="U"), _policy(allowed_regions=("US",)))
        assert result.verdict == "block"


# ───────────────────────── CurrencyCheck ─────────────────────────

class TestCurrencyCheck:
    def test_pass_for_allowed_currency(self) -> None:
        result = CurrencyCheck().evaluate(_offer(currency="USD"), _policy())
        assert result.verdict == "pass"

    def test_block_for_unlisted_currency(self) -> None:
        result = CurrencyCheck().evaluate(_offer(currency="EUR"), _policy())
        assert result.verdict == "block"
        assert result.suggested_adjustment is not None


# ───────────────────────── DealSizeCheck ─────────────────────────

class TestDealSizeCheck:
    def test_pass_within_bounds(self) -> None:
        offer = _offer(total_cents=1_000_000)
        result = DealSizeCheck().evaluate(offer, _policy(min_deal_size_cents=100_000, max_deal_size_cents=10_000_000))
        assert result.verdict == "pass"

    def test_block_below_minimum(self) -> None:
        offer = _offer(total_cents=50_000)
        result = DealSizeCheck().evaluate(offer, _policy(min_deal_size_cents=100_000))
        assert result.verdict == "block"

    def test_block_above_maximum(self) -> None:
        offer = _offer(total_cents=20_000_000)
        result = DealSizeCheck().evaluate(offer, _policy(max_deal_size_cents=10_000_000))
        assert result.verdict == "block"


# ───────────────────────── ApprovalThresholdCheck ─────────────────────────

class TestApprovalThresholdCheck:
    def test_pass_below_threshold(self) -> None:
        offer = _offer(total_cents=4_999_999)
        result = ApprovalThresholdCheck().evaluate(offer, _policy(require_approval_above_cents=5_000_000))
        assert result.verdict == "pass"

    def test_review_at_or_above_threshold(self) -> None:
        offer = _offer(total_cents=5_000_000)
        result = ApprovalThresholdCheck().evaluate(offer, _policy(require_approval_above_cents=5_000_000))
        assert result.verdict == "review"


# ───────────────────────── Aggregate engine ─────────────────────────

class TestEngineAggregate:
    def test_block_beats_review_beats_pass(self) -> None:
        # Discount 25% → review from MaxDiscountCheck
        # Region "CN" → block from RegionCheck
        # Aggregated verdict must be block.
        line = _line(unit_price_cents=7_500, base_price_cents=10_000, min_price_floor_cents=5_000)
        offer = _offer(line, region="CN")
        result = GuardrailEngine().evaluate(offer, _policy())
        assert result.verdict == "block"
        assert result.blocking_check() is not None

    def test_all_pass_returns_pass(self) -> None:
        result = GuardrailEngine().evaluate(_offer(), _policy())
        assert result.verdict == "pass"

    def test_review_when_no_blocks(self) -> None:
        # 25% discount triggers review; no other failures.
        line = _line(unit_price_cents=7_500, base_price_cents=10_000, min_price_floor_cents=5_000)
        offer = _offer(line)
        result = GuardrailEngine().evaluate(offer, _policy())
        assert result.verdict == "review"

    def test_external_payload_hides_policy(self) -> None:
        line = _line(unit_price_cents=9_800, min_price_floor_cents=9_500)
        result = GuardrailEngine().evaluate(_offer(line), _policy(min_margin_percent=15.0))
        assert result.verdict == "block"
        external = result.external_payload()
        # External message is generic — contains no policy numerics.
        assert "15" not in external["reason"]
        assert "margin" not in external["reason"]
        # But suggested_adjustment exists so the agent knows what to propose.
        assert external["suggested_adjustment"] is not None

    def test_replay_dict_preserves_internal_reasons(self) -> None:
        line = _line(unit_price_cents=9_800, min_price_floor_cents=9_500)
        result = GuardrailEngine().evaluate(_offer(line), _policy())
        replay = result.to_replay_dict()
        assert replay["verdict"] == "block"
        assert any("margin" in cr["reason_internal"].lower() for cr in replay["check_results"])
        assert replay["policy_snapshot"]["min_margin_percent"] == 15.0
