"""
ICP scoring — pure deterministic. No ML, no AI.

Scoring happens in two phases:

  1. Hard filters — industry, region, amount range, employee range.
     If the Opp falls outside any specified filter, match_score caps
     at 0 and the filter failure is recorded in match_reasons. Soft
     signals don't compensate.

  2. Soft signals — engagement score + lead source. Each contributes a
     weighted amount toward the final score. Weights default to 1.0
     but the admin can tune between 0 and 2 via the UI.

The returned match_score is a float in [0.0, 1.0] — a weighted average
of the active soft factors normalized by the sum of active weights. When
there are no active soft signals (empty ICP) the score is 0.

match_reasons is a human-readable list the UI renders directly. Each
entry has {factor, status, detail} so the rep can see exactly why a
deal matches or doesn't.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ICPDefinition:
    """Plain-dict shape of an IdealCustomerProfile row. Using a dataclass
    keeps scoring testable without a DB session — the router builds one
    from the SQLAlchemy row and hands it over."""
    id: str
    tenant_id: str
    name: str
    included_industries: list[str] = field(default_factory=list)
    included_regions: list[str] = field(default_factory=list)
    min_amount: float | None = None
    max_amount: float | None = None
    min_employee_count: int | None = None
    max_employee_count: int | None = None
    required_lead_sources: list[str] = field(default_factory=list)
    min_engagement_score: float | None = None
    weight_industry_match: float = 1.0
    weight_region_match: float = 0.8
    weight_amount_fit: float = 1.0
    weight_engagement: float = 1.2
    weight_lead_source: float = 0.7


@dataclass
class ScoringResult:
    match_score: float
    match_reasons: list[dict[str, Any]]


def _get_nested(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _coerce_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def score_opportunity_against_icp(
    opp_data: dict[str, Any],
    icp: ICPDefinition,
) -> ScoringResult:
    """Deterministic match score + human-readable reasons.

    opp_data shape: same as the feature pipeline consumes —
    at minimum `Amount`, `Account.Industry`, `LeadSource`, optional
    `SalesRegion` / `Account.BillingCountry`, optional `NumberOfEmployees`
    on the Account, and the cross-object engagement hints if available.
    """
    reasons: list[dict[str, Any]] = []

    # ─── Hard filters ────────────────────────────────────────────

    industry = str(_get_nested(opp_data, "Account.Industry") or "").strip()
    if icp.included_industries:
        if industry and industry in icp.included_industries:
            reasons.append({
                "factor": "industry", "status": "match",
                "detail": f"{industry} is on the ICP include list.",
            })
        else:
            reasons.append({
                "factor": "industry", "status": "mismatch",
                "detail": (
                    f"{industry or 'Unknown'} not in "
                    f"{icp.included_industries} — hard filter fail."
                ),
            })
            return ScoringResult(match_score=0.0, match_reasons=reasons)

    region = str(
        opp_data.get("SalesRegion")
        or _get_nested(opp_data, "Account.BillingCountry")
        or ""
    ).strip()
    if icp.included_regions:
        if region and region in icp.included_regions:
            reasons.append({
                "factor": "region", "status": "match",
                "detail": f"{region} matches the ICP region list.",
            })
        else:
            reasons.append({
                "factor": "region", "status": "mismatch",
                "detail": (
                    f"{region or 'Unknown'} not in "
                    f"{icp.included_regions} — hard filter fail."
                ),
            })
            return ScoringResult(match_score=0.0, match_reasons=reasons)

    amount = _coerce_float(opp_data.get("Amount"))
    if icp.min_amount is not None and (amount is None or amount < icp.min_amount):
        reasons.append({
            "factor": "amount", "status": "mismatch",
            "detail": f"amount {amount} below ICP minimum {icp.min_amount}.",
        })
        return ScoringResult(match_score=0.0, match_reasons=reasons)
    if icp.max_amount is not None and amount is not None and amount > icp.max_amount:
        reasons.append({
            "factor": "amount", "status": "mismatch",
            "detail": f"amount {amount} above ICP maximum {icp.max_amount}.",
        })
        return ScoringResult(match_score=0.0, match_reasons=reasons)
    if (icp.min_amount is not None or icp.max_amount is not None) and amount is not None:
        reasons.append({
            "factor": "amount", "status": "match",
            "detail": f"amount ${amount:,.0f} within ICP range.",
        })

    employees = opp_data.get("NumberOfEmployees") \
        or _get_nested(opp_data, "Account.NumberOfEmployees")
    employees = _coerce_float(employees)
    if icp.min_employee_count is not None:
        if employees is None or employees < icp.min_employee_count:
            reasons.append({
                "factor": "employee_count", "status": "mismatch",
                "detail": (
                    f"employee count {employees or 'unknown'} below ICP minimum "
                    f"{icp.min_employee_count}."
                ),
            })
            return ScoringResult(match_score=0.0, match_reasons=reasons)
    if icp.max_employee_count is not None and employees is not None \
            and employees > icp.max_employee_count:
        reasons.append({
            "factor": "employee_count", "status": "mismatch",
            "detail": (
                f"employee count {employees} above ICP maximum "
                f"{icp.max_employee_count}."
            ),
        })
        return ScoringResult(match_score=0.0, match_reasons=reasons)

    # ─── Soft signals (weighted) ─────────────────────────────────

    total_weight = 0.0
    weighted_sum = 0.0

    # Industry match — only counts if the filter isn't pinning it anyway.
    if icp.weight_industry_match > 0 and icp.included_industries:
        total_weight += icp.weight_industry_match
        weighted_sum += icp.weight_industry_match  # already in include list (hard-filter passed)

    # Region match — same shape.
    if icp.weight_region_match > 0 and icp.included_regions:
        total_weight += icp.weight_region_match
        weighted_sum += icp.weight_region_match

    # Amount fit — score 1.0 if amount is inside range, partial if one bound
    # is missing, 0 if both bounds missing (feature not used).
    if icp.weight_amount_fit > 0 and (
        icp.min_amount is not None or icp.max_amount is not None
    ):
        total_weight += icp.weight_amount_fit
        if amount is not None:
            weighted_sum += icp.weight_amount_fit   # already within range
        # else: missing amount contributes 0 to weighted_sum but weight stays

    # Engagement signal — pulled from cross-object activity counts baked in
    # by the fetch pipeline. Normalized into [0, 1] with a soft curve so
    # 10 recent activities ≈ full credit.
    engagement_raw = (
        len(opp_data.get("_contact_activities") or [])
        + len(opp_data.get("_account_activities") or [])
    )
    engagement_score = min(1.0, engagement_raw / 15.0)
    if icp.min_engagement_score is not None:
        if engagement_score < icp.min_engagement_score:
            reasons.append({
                "factor": "engagement", "status": "mismatch",
                "detail": (
                    f"engagement {engagement_score:.2f} below ICP threshold "
                    f"{icp.min_engagement_score:.2f}."
                ),
            })
            return ScoringResult(match_score=0.0, match_reasons=reasons)
    if icp.weight_engagement > 0:
        total_weight += icp.weight_engagement
        weighted_sum += icp.weight_engagement * engagement_score
        reasons.append({
            "factor": "engagement",
            "status": "match" if engagement_score >= 0.5 else "partial",
            "detail": f"{engagement_raw} activities across Contact+Account.",
        })

    # Lead-source match.
    lead_source = str(opp_data.get("LeadSource") or "").strip()
    if icp.required_lead_sources:
        if lead_source in icp.required_lead_sources:
            if icp.weight_lead_source > 0:
                total_weight += icp.weight_lead_source
                weighted_sum += icp.weight_lead_source
            reasons.append({
                "factor": "lead_source", "status": "match",
                "detail": f"{lead_source} matches ICP lead source preference.",
            })
        else:
            if icp.weight_lead_source > 0:
                total_weight += icp.weight_lead_source
                # No credit — lead source is a preference, not a hard filter.
            reasons.append({
                "factor": "lead_source", "status": "partial",
                "detail": (
                    f"{lead_source or 'Unknown'} not in preferred sources "
                    f"{icp.required_lead_sources}."
                ),
            })

    # Empty ICP (no hard filters + all weights zero) yields 0 — which is
    # what the UI will render as "configure your ICP".
    if total_weight <= 0:
        return ScoringResult(match_score=0.0, match_reasons=reasons)

    score = weighted_sum / total_weight
    # Clamp in case of rounding drift.
    score = max(0.0, min(1.0, score))
    return ScoringResult(match_score=round(score, 4), match_reasons=reasons)
