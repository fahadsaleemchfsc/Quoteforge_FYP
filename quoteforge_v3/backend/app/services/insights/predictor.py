"""
Predictor — runs a trained LightGBM model against a single open Opportunity.

Flow:
  1. Load the tenant's active model + feature column list from its pickle.
  2. Pull the Opportunity + its Activities from SF (or synthetic).
  3. Build the feature frame, one-hot encode against the training columns.
  4. model.predict_proba() → win_probability in [0, 1].
  5. SHAP values → top 3 positive + top 3 negative drivers.
  6. Cache the prediction in DealInsightPrediction.
  7. Kick Haiku explanation off as a background task (non-blocking).
"""
from __future__ import annotations

import asyncio
import json
import logging
import pickle
from datetime import datetime, timezone
from typing import Any

import numpy as np
import shap
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.insights import (
    DealInsightMapping,
    DealInsightModel,
    DealInsightPrediction,
)
from app.services.insights.features import (
    CATEGORICAL_BASE_COLS,
    MappingBundle,
    build_feature_frame,
    one_hot_and_align,
)
from app.services.insights.salesforce_fetch import (
    fetch_activities_for_opportunities,
    fetch_opportunity_by_id,
)
from app.services.insights.trainer import _mapping_to_bundle

logger = logging.getLogger(__name__)


HAIKU_MODEL = "claude-haiku-4-5-20251001"

# Translation from internal ML feature names to human-readable "signals" the
# coaching prompt can reason about. Never pass raw SHAP values or feature
# names (e.g. "industry=Technology") to Haiku — always run them through
# _translate_signal first. owner_id is deliberately absent: per-rep IDs leak
# internal identifiers and aren't actionable coaching signals.
FEATURE_TO_SIGNAL: dict[str, str] = {
    "activity_count": "engagement",
    "days_since_last_activity": "engagement",
    "amount": "deal_size",
    "age_days": "deal_age",
    "days_to_close": "timeline",
    "days_in_stage": "stage_progression",
}
ONE_HOT_PREFIX_SIGNAL: dict[str, str] = {
    "industry": "industry_fit",
    "lead_source": "lead_source",
    "record_type": "deal_type",
}

HAIKU_SYSTEM_PROMPT = """You are writing a short note for a busy sales rep, shown inside their Salesforce Opportunity page. Your job is to explain this deal's likelihood of closing in plain English — the way a seasoned sales coach would talk, not a data scientist.

HARD RULES
- Never mention SHAP values, contributions, weights, feature names, or any technical ML terminology.
- Never include raw numbers like "+7.117" or "-0.473".
- Keep to 2-3 sentences. No longer.
- Use exactly ONE concrete fact from deal_facts (deal size in dollars, activity count, lead source, etc.) to anchor the explanation.
- End with ONE practical next step the rep could take today or this week.

ICP (IDEAL CUSTOMER PROFILE) CONTEXT
You may reference ICP match when it's informative — phrases like "strong ICP fit" or "falls outside typical customer profile" — but only mention it if it adds signal. Don't force it.
- High win probability AND strong ICP match → reinforce confidence.
- High win probability BUT weak ICP match → note the anomaly ("closes well but unusual for your pattern").
- Low win probability AND weak ICP match → suggest disqualifying; focus elsewhere.
- No active ICP ("icp": null) → don't mention ICP at all.

TONE MATCHES CONFIDENCE TIER
- tier = "high": confident, direct. "This deal is strong..." "Likely to close..." "Position looks solid..."
- tier = "medium": balanced, observational. "This deal could go either way..." "Some positive signals, but watch out for..." "Worth a closer look..."
- tier = "low": honest, concerned but constructive. "This deal is at risk..." "Momentum has stalled..." "Needs attention..."

TRANSLATE SIGNALS INTO HUMAN LANGUAGE
- "engagement" → "the customer has been responsive" / "strong customer engagement" / (if risk) "limited customer engagement"
- "deal_size" → mention the dollar amount directly
- "deal_age" → "this deal has been open for {days} days" / "the deal is becoming stale"
- "timeline" → "close date is approaching" / "long runway"
- "stage_progression" → "moving through stages well" / "stuck in current stage"
- "lead_source" → "referral-sourced lead" / "outbound-sourced lead" etc.
- "industry_fit" → "{industry} deals historically close well" / "less typical for your win pattern"

NEXT-STEP EXAMPLES (pick one matching the context)
- High confidence: "Schedule a closing conversation this week." "Lock in the next milestone while momentum is strong." "Send the proposal and push for sign-off."
- Medium confidence: "Validate timeline with the buyer." "Re-engage the decision-maker to confirm urgency." "Review the proposal details before next meeting."
- Low confidence: "Schedule a discovery call to revive momentum." "Confirm whether the deal is still real or needs disqualifying." "Escalate to manager for a second look."

The rep already knows their deal. Give them your read on it, and a concrete action — nothing else."""


class PredictionError(Exception):
    """Raised when the tenant has no active model or data fetch fails."""

    def __init__(self, message: str, *, code: str = "prediction_error") -> None:
        super().__init__(message)
        self.code = code


# ─── Entry point ────────────────────────────────────────────────────

async def predict_for_opportunity(
    tenant_id: str,
    opportunity_id: str,
    *,
    use_cache: bool = True,
    generate_explanation: bool = True,
) -> DealInsightPrediction:
    async with async_session() as db:
        active = await _load_active_model_row(db, tenant_id)
        if active is None:
            raise PredictionError(
                "No active Deal Insights model for this tenant. "
                "Complete the setup wizard and train a model first.",
                code="no_model",
            )

        if use_cache:
            cached = await _load_cached(db, tenant_id, opportunity_id, active.version)
            if cached is not None:
                # ICP is NOT persisted on the prediction row (it can mutate
                # independently of predictions) — recompute it against the
                # current active ICP on every cache hit. Cheap: pure-function
                # scoring, no network calls once the Opp data is in memory.
                try:
                    mapping_row_cached = await _load_mapping(db, tenant_id)
                    bundle_cached = (_mapping_to_bundle(mapping_row_cached)
                                     if mapping_row_cached else None)
                    if bundle_cached is not None:
                        opp_cached = await fetch_opportunity_by_id(
                            tenant_id=tenant_id, mapping=bundle_cached,
                            opportunity_id=opportunity_id,
                        )
                        if opp_cached is not None:
                            cached.__dict__["_icp"] = await _compute_icp_for_opp(
                                tenant_id, opp_cached,
                            )
                except Exception as e:
                    logger.info("insights.predict: ICP refresh on cache failed (%s)", e)
                return cached

        mapping_row = await _load_mapping(db, tenant_id)
        if mapping_row is None:
            raise PredictionError("Mapping missing — re-run setup wizard.", code="mapping_missing")
        bundle = _mapping_to_bundle(mapping_row)

    opp = await fetch_opportunity_by_id(
        tenant_id=tenant_id, mapping=bundle, opportunity_id=opportunity_id,
    )
    if opp is None:
        raise PredictionError(
            f"Opportunity {opportunity_id} not found in Salesforce.",
            code="opportunity_not_found",
        )

    activities = await fetch_activities_for_opportunities(
        tenant_id=tenant_id, opportunity_ids=[opportunity_id],
    )

    # Load the model bundle from pickle.
    with open(active.model_path, "rb") as f:
        bundle_pkl = pickle.load(f)
    model = bundle_pkl["model"]
    feature_columns: list[str] = bundle_pkl["feature_columns"]
    custom_categorical: list[str] = bundle_pkl.get("custom_categorical_cols", [])

    df = build_feature_frame([opp], activities, bundle)
    # Removed from inference: training data has closed deals with negative
    # `expected_close_distance` values; inference runs on open deals where
    # the value is positive. The model extrapolates incorrectly and ends up
    # treating future close dates as a risk factor. Phase 2 deferred: train
    # on open-deal snapshots instead. For now we zero the column at inference
    # so it lands at the learned median for closed rows.
    if "expected_close_distance" in df.columns:
        df["expected_close_distance"] = 0
    X = one_hot_and_align(
        df,
        categorical_cols=CATEGORICAL_BASE_COLS,
        custom_categorical_cols=custom_categorical,
        reference_columns=feature_columns,
    )

    prob = float(model.predict_proba(X)[:, 1][0])
    drivers = _compute_drivers(model, X, feature_columns)

    # Confidence range — early_stage tenants use bootstrap-resample models;
    # standard+ use per-tree variance. Both are best-effort — if the cache
    # isn't warm we skip gracefully and the UI falls back to a point estimate.
    prob_lower: float | None = None
    prob_upper: float | None = None
    try:
        from app.services.insights.bootstrap import (
            predict_range_via_per_tree,
            predict_range_via_resample,
        )
        from app.services.insights.trainer import MODEL_STORAGE_ROOT

        tier = active.data_quality_tier or "standard"
        if tier == "early_stage":
            rng = predict_range_via_resample(
                X, tenant_id=tenant_id, model_root=MODEL_STORAGE_ROOT,
            )
        else:
            rng = predict_range_via_per_tree(model, X)
        if rng is not None:
            prob_lower, prob_upper = rng
    except Exception as e:
        logger.info("insights.predict: confidence range unavailable (%s)", e)

    # Persist prediction (unique per tenant+opp+model_version; upsert by delete+insert).
    async with async_session() as db:
        await db.execute(
            delete(DealInsightPrediction).where(
                DealInsightPrediction.tenant_id == tenant_id,
                DealInsightPrediction.sf_opportunity_id == opportunity_id,
                DealInsightPrediction.model_version == active.version,
            )
        )
        row = DealInsightPrediction(
            tenant_id=tenant_id,
            model_version=active.version,
            sf_opportunity_id=opportunity_id,
            win_probability=prob,
            probability_lower=prob_lower,
            probability_upper=prob_upper,
            predicted_at=datetime.now(timezone.utc),
        )
        row.top_drivers_list = drivers
        db.add(row)
        await db.commit()
        await db.refresh(row)

    # Phase 3 — compute ICP match alongside the win probability. Best-effort:
    # a tenant with no active ICP returns icp_snapshot=None and the LWC just
    # renders the win probability (no crash).
    icp_snapshot: dict[str, Any] | None = None
    try:
        icp_snapshot = await _compute_icp_for_opp(tenant_id, opp)
    except Exception as e:
        logger.info("insights.predict: ICP score skipped (%s)", e)

    if generate_explanation and settings.ANTHROPIC_API_KEY:
        feature_row = df.iloc[0].to_dict()
        deal_facts = _build_deal_facts(feature_row, opp, bundle)
        asyncio.create_task(
            _populate_explanation(row.id, prob, drivers, deal_facts, icp_snapshot),
        )

    # Attach ICP info to the returned row so the router can surface it on
    # the PredictionResponse without a second round-trip.
    row.__dict__["_icp"] = icp_snapshot
    return row


async def _compute_icp_for_opp(
    tenant_id: str, opp: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve active ICP (if any) + score it against this Opp. Returns a
    minimal snapshot the caller can hand to Haiku + the LWC."""
    from app.models.icp import IdealCustomerProfile
    from app.services.icp.scorer import (
        ICPDefinition, score_opportunity_against_icp,
    )
    async with async_session() as db:
        row = (await db.execute(
            select(IdealCustomerProfile).where(
                IdealCustomerProfile.tenant_id == tenant_id,
                IdealCustomerProfile.is_active.is_(True),
            )
        )).scalars().first()
    if row is None:
        return None
    definition = ICPDefinition(
        id=row.id, tenant_id=row.tenant_id, name=row.name,
        included_industries=row.included_industries_list,
        included_regions=row.included_regions_list,
        min_amount=row.min_amount, max_amount=row.max_amount,
        min_employee_count=row.min_employee_count,
        max_employee_count=row.max_employee_count,
        required_lead_sources=row.required_lead_sources_list,
        min_engagement_score=row.min_engagement_score,
        weight_industry_match=row.weight_industry_match,
        weight_region_match=row.weight_region_match,
        weight_amount_fit=row.weight_amount_fit,
        weight_engagement=row.weight_engagement,
        weight_lead_source=row.weight_lead_source,
    )
    result = score_opportunity_against_icp(opp, definition)
    return {
        "icp_id": row.id, "icp_name": row.name,
        "match_score": result.match_score,
        "match_percent": int(round(result.match_score * 100)),
        "band": ("strong" if result.match_score >= 0.7
                 else "partial" if result.match_score >= 0.4 else "weak"),
        "match_reasons": result.match_reasons,
    }


async def generate_explanation_with_haiku(
    *,
    probability: float,
    drivers: list[dict[str, Any]],
    deal_facts: dict[str, Any],
    icp: dict[str, Any] | None = None,
) -> str | None:
    """Call Claude Haiku with prompt caching. Returns None on any failure so
    the caller can defer and show a placeholder in the UI.

    Important: we DO NOT pass raw SHAP values or feature names to the model.
    Drivers are translated to coarse "signals" (engagement, deal_size, ...)
    and the model is given concrete deal facts it can cite — this is what
    keeps the output rep-facing instead of reading like a data-science report.
    """
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        tier = _confidence_tier(probability)
        positive_signals, risk_signals = _split_signals(drivers)
        pct = int(round(probability * 100))
        facts_json = json.dumps(deal_facts, default=str, sort_keys=True)

        # Extract a compact ICP line. Pass `null` when no active ICP so the
        # model's hard rule ("don't mention it") fires.
        if icp:
            top_reasons = [
                f"{r.get('factor')}={r.get('status')}"
                for r in (icp.get("match_reasons") or [])[:2]
            ]
            icp_line = (
                f"- ICP match: {icp['match_percent']}% ({icp['band']} fit; "
                f"{', '.join(top_reasons) or 'no reasons'})\n"
            )
        else:
            icp_line = '- ICP match: null (no active ICP configured)\n'

        user_msg = (
            f"Deal summary:\n"
            f"- Win probability: {pct}% ({tier} confidence)\n"
            + icp_line +
            f"- Deal facts: {facts_json}\n"
            f"- Positive signals: {positive_signals}\n"
            f"- Risk signals: {risk_signals}\n\n"
            f"Write the 2-3 sentence explanation now."
        )

        resp = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            system=[{
                "type": "text",
                "text": HAIKU_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        return text or None
    except Exception as e:
        logger.info("insights.explain: haiku call failed (%s)", e)
        return None


# ─── Rep-facing translation helpers ─────────────────────────────────

def _confidence_tier(prob: float) -> str:
    if prob < 0.4:
        return "low"
    if prob > 0.7:
        return "high"
    return "medium"


def _translate_signal(feature_name: str) -> str | None:
    """Map an internal feature name to a coaching signal. Returns None if the
    feature should be omitted entirely (e.g. owner_id one-hots)."""
    if feature_name in FEATURE_TO_SIGNAL:
        return FEATURE_TO_SIGNAL[feature_name]
    if "=" in feature_name:
        base = feature_name.split("=", 1)[0]
        if base == "owner_id":
            return None
        return ONE_HOT_PREFIX_SIGNAL.get(base)
    return None


def _split_signals(
    drivers: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Partition drivers into positive/risk signal lists. Dedupes within each
    list, preserves order. owner_id and unknown features are dropped."""
    positive: list[str] = []
    risks: list[str] = []
    for d in drivers:
        sig = _translate_signal(d.get("feature", ""))
        if sig is None:
            continue
        target = positive if d.get("direction") == "positive" else risks
        if sig not in target:
            target.append(sig)
    return positive, risks


def _build_deal_facts(
    feature_row: dict[str, Any],
    opp: dict[str, Any],
    mapping: MappingBundle,
) -> dict[str, Any]:
    """Assemble the concrete rep-facing facts Haiku can cite. Uses the
    already-computed feature row so the numbers match what the model saw."""
    facts: dict[str, Any] = {
        "amount_usd": int(round(float(feature_row.get("amount") or 0))),
        "recent_activities": int(feature_row.get("activity_count") or 0),
        "days_open": int(feature_row.get("age_days") or 0),
        "lead_source": str(feature_row.get("lead_source") or "Unknown"),
        "industry": str(feature_row.get("industry") or "Unknown"),
        "stage": str(opp.get(mapping.stage_field) or "Unknown"),
    }
    for cf in mapping.custom_fields:
        name = cf.get("feature_name")
        if not name or name in facts:
            continue
        val = feature_row.get(name)
        if val is None:
            continue
        kind = cf.get("type")
        if kind == "numeric":
            try:
                facts[name] = float(val)
            except (TypeError, ValueError):
                facts[name] = val
        elif kind == "boolean":
            facts[name] = bool(val)
        else:
            facts[name] = str(val)
    return facts


# ─── Internals ─────────────────────────────────────────────────────

async def _load_active_model_row(
    db: AsyncSession, tenant_id: str,
) -> DealInsightModel | None:
    res = await db.execute(
        select(DealInsightModel)
        .where(
            DealInsightModel.tenant_id == tenant_id,
            DealInsightModel.is_active.is_(True),
        )
        .order_by(DealInsightModel.version.desc())
    )
    return res.scalars().first()


async def _load_mapping(db: AsyncSession, tenant_id: str) -> DealInsightMapping | None:
    res = await db.execute(
        select(DealInsightMapping).where(DealInsightMapping.tenant_id == tenant_id)
    )
    return res.scalar_one_or_none()


async def _load_cached(
    db: AsyncSession, tenant_id: str, opp_id: str, version: int,
) -> DealInsightPrediction | None:
    res = await db.execute(
        select(DealInsightPrediction).where(
            DealInsightPrediction.tenant_id == tenant_id,
            DealInsightPrediction.sf_opportunity_id == opp_id,
            DealInsightPrediction.model_version == version,
        )
    )
    return res.scalar_one_or_none()


def _compute_drivers(
    model: Any,
    X: Any,
    feature_columns: list[str],
) -> list[dict[str, Any]]:
    """Compute SHAP values for a single row and return top 3 positive + top 3
    negative drivers sorted by absolute value.

    SHAP's TreeExplainer on LightGBM for binary classification returns a single
    array whose sign indicates contribution toward class 1 (win).
    """
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
        # LightGBM binary: shap_values may be list [neg, pos] OR a single 2D array.
        if isinstance(shap_values, list) and len(shap_values) == 2:
            row = np.asarray(shap_values[1])[0]
        else:
            row = np.asarray(shap_values)[0]
            if row.ndim == 2 and row.shape[1] == 2:
                row = row[:, 1]
    except Exception as e:
        logger.info("insights.predict: SHAP failed (%s), falling back to gain importance", e)
        # Fallback: use feature importance × feature value sign as a crude proxy.
        importances = np.asarray(model.feature_importances_, dtype=float)
        total = importances.sum() or 1.0
        row = importances / total

    # Filter features we deliberately ignore at inference. `expected_close_distance`
    # is zeroed before predict (see Session 6.5 Step 1) because its training
    # distribution doesn't generalize — surfacing it as a driver would be
    # misleading. The model's probability no longer depends on it, but SHAP
    # will still attribute value; we drop it here so reps don't see it.
    INFERENCE_DRIVER_BLACKLIST = {"expected_close_distance"}
    pairs = [
        (feature_columns[i], float(row[i]))
        for i in range(len(feature_columns))
        if feature_columns[i] not in INFERENCE_DRIVER_BLACKLIST
    ]
    positives = sorted([p for p in pairs if p[1] > 0], key=lambda p: p[1], reverse=True)[:3]
    negatives = sorted([p for p in pairs if p[1] < 0], key=lambda p: p[1])[:3]
    return [
        {"feature": f, "shap_value": round(v, 4), "direction": "positive"}
        for f, v in positives
    ] + [
        {"feature": f, "shap_value": round(v, 4), "direction": "negative"}
        for f, v in negatives
    ]


async def _populate_explanation(
    prediction_id: str,
    probability: float,
    drivers: list[dict[str, Any]],
    deal_facts: dict[str, Any],
    icp: dict[str, Any] | None = None,
) -> None:
    """Background task — generate the Haiku explanation + persist it."""
    text = await generate_explanation_with_haiku(
        probability=probability, drivers=drivers,
        deal_facts=deal_facts, icp=icp,
    )
    if not text:
        return
    async with async_session() as db:
        res = await db.execute(
            select(DealInsightPrediction).where(DealInsightPrediction.id == prediction_id)
        )
        row = res.scalar_one_or_none()
        if row is None:
            return
        row.explanation_text = text
        await db.commit()
