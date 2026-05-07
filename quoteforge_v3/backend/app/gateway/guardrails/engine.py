"""
Guardrail Engine — deterministic offer validation.

Contract:
  engine.evaluate(offer) -> EngineResult
    where EngineResult carries:
      - verdict: "pass" | "review" | "block"
      - check_results: every check's verdict (internal reasons preserved)
      - suggested_adjustment: on block, a per-SKU hint of what prices would pass
      - policy_snapshot: the policy values used, for replay-safe logging

Determinism:
  - No randomness, no I/O inside the engine.
  - Same (OfferContext, PolicySnapshot) tuple always produces the same result.
  - Callers load the policy once and pass a PolicySnapshot — the engine never
    touches the DB. This is what makes it unit-testable without any fixtures.

Internal / external reasons:
  - `reason_internal` is what admins see in the Replay Layer.
  - `reason_external` is the generic buyer-agent-facing message. It NEVER
    reveals policy values. The only leakage to the buyer is
    `suggested_adjustment`, which shows acceptable price ranges without
    naming the rule that fired.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol

Verdict = Literal["pass", "review", "block"]

# Severity ordering — highest wins during aggregation.
_VERDICT_RANK: dict[Verdict, int] = {"pass": 0, "review": 1, "block": 2}

# External messages deliberately avoid revealing the policy.
EXTERNAL_MSG_GENERIC_BLOCK = "offer exceeds allowed parameters"
EXTERNAL_MSG_REGION_BLOCK = "seller does not transact in the specified region"
EXTERNAL_MSG_CURRENCY_BLOCK = "seller does not transact in the specified currency"
EXTERNAL_MSG_REVIEW = "offer requires seller review before commitment"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineItemContext:
    """One line item normalized for evaluation. Prices are integer cents."""
    sku: str
    quantity: int
    unit_price_cents: int
    base_price_cents: int
    min_price_floor_cents: int

    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity

    def discount_percent(self) -> float:
        if self.base_price_cents == 0:
            return 0.0
        return (self.base_price_cents - self.unit_price_cents) / self.base_price_cents * 100.0

    def margin_percent(self) -> float:
        """Margin above the floor, as a percent of unit_price. 0 if floor==price."""
        if self.unit_price_cents == 0:
            return 0.0
        return (self.unit_price_cents - self.min_price_floor_cents) / self.unit_price_cents * 100.0


@dataclass(frozen=True)
class OfferContext:
    """Everything the engine needs to decide a verdict. No DB access after this."""
    tenant_id: str                       # Tenant.id UUID
    line_items: tuple[LineItemContext, ...]
    total_cents: int
    currency: str
    buyer_region: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicySnapshot:
    """Snapshot of GuardrailPolicy at a point in time — serializable.

    Stored verbatim in Replay Layer so historical evaluations can be replayed
    even after the live policy changes.
    """
    min_margin_percent: float
    max_discount_percent: float
    max_discount_with_approval_percent: float
    allowed_regions: tuple[str, ...]
    currency_allowlist: tuple[str, ...]
    min_deal_size_cents: int
    max_deal_size_cents: int | None
    require_approval_above_cents: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert tuples for JSON serialization.
        d["allowed_regions"] = list(self.allowed_regions)
        d["currency_allowlist"] = list(self.currency_allowlist)
        return d


@dataclass(frozen=True)
class CheckResult:
    name: str
    verdict: Verdict
    reason_internal: str
    reason_external: str
    suggested_adjustment: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineResult:
    verdict: Verdict
    check_results: tuple[CheckResult, ...]
    policy_snapshot: PolicySnapshot

    def blocking_check(self) -> CheckResult | None:
        for cr in self.check_results:
            if cr.verdict == "block":
                return cr
        return None

    def external_payload(self) -> dict[str, Any]:
        """Shape returned to buyer agents on block/review. Policy-free."""
        block = self.blocking_check()
        if block is not None:
            return {
                "verdict": "block",
                "reason": block.reason_external,
                "suggested_adjustment": block.suggested_adjustment,
            }
        if self.verdict == "review":
            return {
                "verdict": "review",
                "reason": EXTERNAL_MSG_REVIEW,
            }
        return {"verdict": "pass"}

    def to_replay_dict(self) -> dict[str, Any]:
        """Full breakdown for the Replay Layer — includes internal reasons."""
        return {
            "verdict": self.verdict,
            "check_results": [cr.to_dict() for cr in self.check_results],
            "policy_snapshot": self.policy_snapshot.to_dict(),
        }


# ---------------------------------------------------------------------------
# Check protocol + concrete checks
# ---------------------------------------------------------------------------

class GuardrailCheck(Protocol):
    name: str

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult: ...


def _pass(name: str) -> CheckResult:
    return CheckResult(
        name=name, verdict="pass",
        reason_internal="within limits",
        reason_external="",
    )


class MinMarginCheck:
    """Blocks if any line's margin above the min_price_floor falls below policy."""
    name = "min_margin"

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult:
        violations: list[dict[str, Any]] = []
        for line in offer.line_items:
            margin = line.margin_percent()
            if margin < policy.min_margin_percent:
                # Compute the unit price that would satisfy margin exactly.
                # floor / (1 - min_margin/100) rounded up to cent.
                ratio = 1.0 - policy.min_margin_percent / 100.0
                if ratio <= 0:
                    min_acceptable = line.base_price_cents
                else:
                    min_acceptable = int(Decimal(line.min_price_floor_cents) / Decimal(ratio))
                    # Guard against floating-point undershoot by +1 cent if needed.
                    if min_acceptable < line.min_price_floor_cents:
                        min_acceptable = line.min_price_floor_cents
                violations.append({
                    "sku": line.sku,
                    "offered_unit_price_cents": line.unit_price_cents,
                    "min_acceptable_unit_price_cents": min_acceptable,
                })
        if not violations:
            return _pass(self.name)
        return CheckResult(
            name=self.name, verdict="block",
            reason_internal=(
                f"margin floor {policy.min_margin_percent:.2f}% violated on "
                f"{[v['sku'] for v in violations]}"
            ),
            reason_external=EXTERNAL_MSG_GENERIC_BLOCK,
            suggested_adjustment={"line_items": violations},
        )


class MaxDiscountCheck:
    """Blocks if discount > hard ceiling; flags review if > auto-approve threshold."""
    name = "max_discount"

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult:
        blocked: list[dict[str, Any]] = []
        review: list[dict[str, Any]] = []
        for line in offer.line_items:
            discount = line.discount_percent()
            if discount > policy.max_discount_with_approval_percent:
                min_acceptable = int(
                    Decimal(line.base_price_cents)
                    * (1 - Decimal(str(policy.max_discount_with_approval_percent)) / 100)
                )
                blocked.append({
                    "sku": line.sku,
                    "offered_unit_price_cents": line.unit_price_cents,
                    "min_acceptable_unit_price_cents": min_acceptable,
                })
            elif discount > policy.max_discount_percent:
                review.append({
                    "sku": line.sku,
                    "discount_percent": round(discount, 2),
                })
        if blocked:
            return CheckResult(
                name=self.name, verdict="block",
                reason_internal=(
                    f"discount ceiling {policy.max_discount_with_approval_percent:.2f}% "
                    f"exceeded on {[b['sku'] for b in blocked]}"
                ),
                reason_external=EXTERNAL_MSG_GENERIC_BLOCK,
                suggested_adjustment={"line_items": blocked},
            )
        if review:
            return CheckResult(
                name=self.name, verdict="review",
                reason_internal=(
                    f"discount above auto-approve threshold {policy.max_discount_percent:.2f}% "
                    f"on {[r['sku'] for r in review]}"
                ),
                reason_external=EXTERNAL_MSG_REVIEW,
            )
        return _pass(self.name)


class RegionCheck:
    """Strict equality — no substring matching. `allowed_regions` is authoritative."""
    name = "region"

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult:
        region = (offer.buyer_region or "").strip().upper()
        allowed = {r.strip().upper() for r in policy.allowed_regions}
        if region in allowed:
            return _pass(self.name)
        return CheckResult(
            name=self.name, verdict="block",
            reason_internal=f"region '{region}' not in allowlist {sorted(allowed)}",
            reason_external=EXTERNAL_MSG_REGION_BLOCK,
            suggested_adjustment={"allowed_regions": sorted(allowed)},
        )


class CurrencyCheck:
    name = "currency"

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult:
        currency = (offer.currency or "").strip().upper()
        allowed = {c.strip().upper() for c in policy.currency_allowlist}
        if currency in allowed:
            return _pass(self.name)
        return CheckResult(
            name=self.name, verdict="block",
            reason_internal=f"currency '{currency}' not in allowlist {sorted(allowed)}",
            reason_external=EXTERNAL_MSG_CURRENCY_BLOCK,
            suggested_adjustment={"allowed_currencies": sorted(allowed)},
        )


class DealSizeCheck:
    name = "deal_size"

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult:
        total = offer.total_cents
        if total < policy.min_deal_size_cents:
            return CheckResult(
                name=self.name, verdict="block",
                reason_internal=f"total {total} below min_deal_size {policy.min_deal_size_cents}",
                reason_external=EXTERNAL_MSG_GENERIC_BLOCK,
                suggested_adjustment=None,
            )
        if policy.max_deal_size_cents is not None and total > policy.max_deal_size_cents:
            return CheckResult(
                name=self.name, verdict="block",
                reason_internal=f"total {total} above max_deal_size {policy.max_deal_size_cents}",
                reason_external=EXTERNAL_MSG_GENERIC_BLOCK,
                suggested_adjustment=None,
            )
        return _pass(self.name)


class ApprovalThresholdCheck:
    """Flags review when total crosses the human-review threshold. Never blocks."""
    name = "approval_threshold"

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> CheckResult:
        if offer.total_cents >= policy.require_approval_above_cents:
            return CheckResult(
                name=self.name, verdict="review",
                reason_internal=(
                    f"total {offer.total_cents} >= approval threshold "
                    f"{policy.require_approval_above_cents}"
                ),
                reason_external=EXTERNAL_MSG_REVIEW,
            )
        return _pass(self.name)


DEFAULT_CHECKS: tuple[GuardrailCheck, ...] = (
    MinMarginCheck(),
    MaxDiscountCheck(),
    RegionCheck(),
    CurrencyCheck(),
    DealSizeCheck(),
    ApprovalThresholdCheck(),
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class GuardrailEngine:
    """Composes a list of checks into a single evaluate() call."""

    def __init__(self, checks: tuple[GuardrailCheck, ...] = DEFAULT_CHECKS) -> None:
        self._checks = checks

    def evaluate(self, offer: OfferContext, policy: PolicySnapshot) -> EngineResult:
        results = tuple(c.evaluate(offer, policy) for c in self._checks)
        # Aggregate to highest-severity verdict.
        overall: Verdict = "pass"
        for cr in results:
            if _VERDICT_RANK[cr.verdict] > _VERDICT_RANK[overall]:
                overall = cr.verdict
        return EngineResult(
            verdict=overall,
            check_results=results,
            policy_snapshot=policy,
        )


# ---------------------------------------------------------------------------
# Snapshot loader — the ONLY place that bridges ORM model to pure-data snapshot
# ---------------------------------------------------------------------------

def snapshot_from_orm(policy_row: Any) -> PolicySnapshot:
    """Translate a GuardrailPolicy ORM row to a frozen PolicySnapshot."""
    try:
        regions = tuple(json.loads(policy_row.allowed_regions or "[]"))
    except json.JSONDecodeError:
        regions = ()
    try:
        currencies = tuple(json.loads(policy_row.currency_allowlist or "[]"))
    except json.JSONDecodeError:
        currencies = ()
    return PolicySnapshot(
        min_margin_percent=float(policy_row.min_margin_percent),
        max_discount_percent=float(policy_row.max_discount_percent),
        max_discount_with_approval_percent=float(policy_row.max_discount_with_approval_percent),
        allowed_regions=regions,
        currency_allowlist=currencies,
        min_deal_size_cents=int(policy_row.min_deal_size_cents),
        max_deal_size_cents=(
            int(policy_row.max_deal_size_cents)
            if policy_row.max_deal_size_cents is not None
            else None
        ),
        require_approval_above_cents=int(policy_row.require_approval_above_cents),
    )
