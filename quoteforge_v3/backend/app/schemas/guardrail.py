"""Pydantic schemas for the admin guardrails API and simulator."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


VerdictLiteral = Literal["pass", "review", "block"]


# ---------------------------------------------------------------------------
# GET / PUT /api/tenant/guardrails
# ---------------------------------------------------------------------------

class GuardrailPolicyOut(BaseModel):
    tenant_id: str
    min_margin_percent: Decimal
    max_discount_percent: Decimal
    max_discount_with_approval_percent: Decimal
    allowed_regions: list[str]
    currency_allowlist: list[str]
    min_deal_size_cents: int
    max_deal_size_cents: int | None
    require_approval_above_cents: int
    created_at: datetime
    updated_at: datetime


class GuardrailPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_margin_percent: Decimal | None = Field(default=None, ge=0, le=99, decimal_places=2)
    max_discount_percent: Decimal | None = Field(default=None, ge=0, le=99, decimal_places=2)
    max_discount_with_approval_percent: Decimal | None = Field(
        default=None, ge=0, le=99, decimal_places=2
    )
    allowed_regions: list[str] | None = Field(default=None, min_length=1, max_length=50)
    currency_allowlist: list[str] | None = Field(default=None, min_length=1, max_length=20)
    min_deal_size_cents: int | None = Field(default=None, ge=0)
    max_deal_size_cents: int | None = Field(default=None, ge=0)
    require_approval_above_cents: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# POST /api/tenant/guardrails/simulate
# ---------------------------------------------------------------------------

class SimulateLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=1_000_000)
    unit_price: Decimal = Field(ge=0, decimal_places=2)


class SimulateRequest(BaseModel):
    """
    Admin-only preview: resolve each sku against the product catalog (to pull
    base_price + floor), pretend the admin proposed `unit_price`, then evaluate.
    Does NOT persist a draft.
    """
    model_config = ConfigDict(extra="forbid")

    buyer_region: str = Field(min_length=2, max_length=10, default="US")
    currency: str = Field(min_length=3, max_length=3, default="USD")
    line_items: list[SimulateLineItem] = Field(min_length=1, max_length=50)
    use_ai: bool = Field(
        default=False,
        description=(
            "If true, ignores the admin's proposed unit_prices and runs the "
            "NegotiationService to get its proposal, then evaluates. Returns "
            "the attempt chain alongside the final verdict."
        ),
    )
    buyer_deal_name: str = Field(
        default="", max_length=200,
        description=(
            "Optional — passed through to the AI context (and the stub backend "
            "reads magic 'stub:*' prefixes from here to steer its behavior)."
        ),
    )


class CheckResultOut(BaseModel):
    name: str
    verdict: VerdictLiteral
    reason_internal: str
    reason_external: str
    suggested_adjustment: dict[str, Any] | None = None


class PolicySnapshotOut(BaseModel):
    min_margin_percent: float
    max_discount_percent: float
    max_discount_with_approval_percent: float
    allowed_regions: list[str]
    currency_allowlist: list[str]
    min_deal_size_cents: int
    max_deal_size_cents: int | None
    require_approval_above_cents: int


class SimulateAttemptOut(BaseModel):
    attempt_number: int
    backend: str
    verdict: str
    blocking_check_names: list[str]
    latency_ms: int
    proposed_unit_prices_cents: dict[str, int] | None = None
    rationale: str | None = None
    confidence: float | None = None
    error: str | None = None


class ImpactPreviewRequest(BaseModel):
    """Proposed policy values the admin is considering applying."""
    model_config = ConfigDict(extra="forbid")

    min_margin_percent: Decimal = Field(ge=0, le=99, decimal_places=2)
    max_discount_percent: Decimal = Field(ge=0, le=99, decimal_places=2)
    max_discount_with_approval_percent: Decimal = Field(ge=0, le=99, decimal_places=2)
    allowed_regions: list[str] = Field(min_length=1, max_length=50)
    currency_allowlist: list[str] = Field(min_length=1, max_length=20)
    min_deal_size_cents: int = Field(ge=0)
    max_deal_size_cents: int | None = Field(default=None, ge=0)
    require_approval_above_cents: int = Field(ge=0)
    window_days: int = Field(default=7, ge=1, le=90)


class ImpactExampleDelta(BaseModel):
    offer_id: str
    client_name: str
    total_cents: int
    was_verdict: VerdictLiteral
    would_verdict: VerdictLiteral
    change: str             # e.g. "pass → block", "block → pass"


class ImpactPreviewResult(BaseModel):
    window_days: int
    events_evaluated: int

    # Current-policy counts.
    current_pass: int
    current_review: int
    current_block: int

    # Under-proposed-policy counts.
    would_pass: int
    would_review: int
    would_block: int

    # Deltas (positive = more under proposed policy).
    delta_pass: int
    delta_review: int
    delta_block: int

    # Aggregate financial deltas in dollars (not cents — UI-friendly).
    revenue_impact: float       # negative = offers that would now block represent $X "lost"
    margin_impact: float        # positive = offers that now satisfy tighter floors sum $X of margin floor headroom

    examples: list[ImpactExampleDelta] = Field(default_factory=list)


class SimulateResult(BaseModel):
    verdict: VerdictLiteral
    check_results: list[CheckResultOut]
    policy_snapshot: PolicySnapshotOut
    # Echo back the resolved line inputs for UI display.
    resolved_line_items: list[dict[str, Any]]
    total_cents: int
    unknown_skus: list[str] = Field(default_factory=list)
    # AI dry-run details (only populated when use_ai=true).
    ai_attempts: list[SimulateAttemptOut] = Field(default_factory=list)
    ai_fell_back: bool = False
    ai_backend: str | None = None
