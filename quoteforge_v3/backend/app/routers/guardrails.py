"""
Admin guardrail policy endpoints + dry-run simulator.

  GET  /api/tenant/guardrails            — read policy
  PUT  /api/tenant/guardrails            — partial update
  POST /api/tenant/guardrails/simulate   — evaluate a hypothetical offer
                                            (full internal reasons returned)

The simulator is the killer admin feature — lets sellers verify their own
rules before production traffic hits them. It writes a ReplayEvent with
event_type=guardrail_simulation so dry-runs are auditable but distinguishable
from real traffic.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant, get_current_user
from app.gateway.adapters.product_adapter import resolve_exposed_skus
from app.gateway.guardrails import GuardrailEngine, LineItemContext, OfferContext
from app.gateway.guardrails.engine import PolicySnapshot, snapshot_from_orm
from app.gateway.guardrails.policy_loader import load_policy_by_slug
from app.gateway.guardrails.replay import record_evaluation
from app.gateway.money import dollars_to_cents
from app.gateway.negotiation import NegotiationContext, NegotiationService
from app.gateway.negotiation.context import NegotiationLine, PolicyHints
from app.models.document_log import DocumentLog
from app.models.guardrail_policy import GuardrailPolicy
from app.models.replay_event import EVENT_GUARDRAIL_EVALUATION, ReplayEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.guardrail import (
    CheckResultOut,
    GuardrailPolicyOut,
    GuardrailPolicyUpdate,
    ImpactExampleDelta,
    ImpactPreviewRequest,
    ImpactPreviewResult,
    PolicySnapshotOut,
    SimulateAttemptOut,
    SimulateRequest,
    SimulateResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenant/guardrails", tags=["guardrails"])


async def _simulate_with_ai(
    *, tenant_id_uuid, tenant_slug, payload, resolved, loaded,
) -> dict:
    """Run NegotiationService in dry-run. Admin-facing — full attempts exposed."""
    snap = loaded.snapshot
    nc = NegotiationContext(
        tenant_id=tenant_id_uuid,
        tenant_slug=tenant_slug,
        buyer_region=payload.buyer_region.upper(),
        buyer_client_name="Simulator",
        buyer_deal_name=payload.buyer_deal_name,
        lines=tuple(
            NegotiationLine(
                sku=li.sku,
                quantity=li.quantity,
                base_price_cents=(dollars_to_cents(resolved[li.sku].base_price)
                                  if li.sku in resolved else 0),
                min_price_floor_cents=(dollars_to_cents(resolved[li.sku].min_price_floor)
                                       if li.sku in resolved else 0),
                product_name=resolved[li.sku].name if li.sku in resolved else li.sku,
            )
            for li in payload.line_items if li.sku in resolved
        ),
        policy_hints=PolicyHints(
            min_margin_percent=snap.min_margin_percent,
            max_discount_percent=snap.max_discount_percent,
            max_discount_with_approval_percent=snap.max_discount_with_approval_percent,
            allowed_regions=snap.allowed_regions,
            currency_allowlist=snap.currency_allowlist,
        ),
    )
    service = NegotiationService()
    validated = await service.propose_and_validate(
        context=nc, policy=snap, currency=payload.currency.upper(),
    )
    attempts_out = [
        SimulateAttemptOut(
            attempt_number=a.attempt_number,
            backend=a.backend,
            verdict=a.verdict,
            blocking_check_names=list(a.blocking_check_names),
            latency_ms=a.latency_ms,
            proposed_unit_prices_cents=(
                {l.sku: l.proposed_unit_price_cents for l in a.proposed.lines}
                if a.proposed else None
            ),
            rationale=a.proposed.rationale if a.proposed else None,
            confidence=a.proposed.confidence if a.proposed else None,
            error=a.error,
        )
        for a in validated.attempts
    ]
    return {
        "final_lines": [
            {"sku": l.sku, "quantity": l.quantity,
             "proposed_unit_price_cents": l.proposed_unit_price_cents}
            for l in validated.final_lines
        ],
        "attempts": attempts_out,
        "fell_back": validated.fell_back,
        "backend": validated.backend_name,
    }


async def _load_policy_or_500(db: AsyncSession, tenant_id: str) -> GuardrailPolicy:
    row = (
        await db.execute(select(GuardrailPolicy).where(GuardrailPolicy.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=500, detail="guardrail policy not provisioned for tenant")
    return row


def _to_out(policy: GuardrailPolicy) -> GuardrailPolicyOut:
    try:
        regions = json.loads(policy.allowed_regions or "[]")
    except json.JSONDecodeError:
        regions = []
    try:
        currencies = json.loads(policy.currency_allowlist or "[]")
    except json.JSONDecodeError:
        currencies = []
    return GuardrailPolicyOut(
        tenant_id=policy.tenant_id,
        min_margin_percent=policy.min_margin_percent,
        max_discount_percent=policy.max_discount_percent,
        max_discount_with_approval_percent=policy.max_discount_with_approval_percent,
        allowed_regions=regions,
        currency_allowlist=currencies,
        min_deal_size_cents=int(policy.min_deal_size_cents),
        max_deal_size_cents=(
            int(policy.max_deal_size_cents) if policy.max_deal_size_cents is not None else None
        ),
        require_approval_above_cents=int(policy.require_approval_above_cents),
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.get("", response_model=GuardrailPolicyOut)
async def get_policy(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> GuardrailPolicyOut:
    policy = await _load_policy_or_500(db, tenant.id)
    return _to_out(policy)


@router.put("", response_model=GuardrailPolicyOut)
async def update_policy(
    payload: GuardrailPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> GuardrailPolicyOut:
    policy = await _load_policy_or_500(db, tenant.id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field in ("allowed_regions", "currency_allowlist"):
            # Normalize to uppercase and dedupe while preserving order.
            seen: list[str] = []
            for v in value or []:
                s = str(v).strip().upper()
                if s and s not in seen:
                    seen.append(s)
            setattr(policy, field, json.dumps(seen))
        else:
            setattr(policy, field, value)

    # Invariant: with-approval ceiling >= no-approval threshold.
    with_appr = Decimal(policy.max_discount_with_approval_percent)
    without_appr = Decimal(policy.max_discount_percent)
    if with_appr < without_appr:
        await db.rollback()
        raise HTTPException(
            status_code=422,
            detail="max_discount_with_approval_percent must be >= max_discount_percent",
        )

    await db.commit()
    await db.refresh(policy)
    logger.info("guardrail policy updated tenant=%s by=%s fields=%s",
                policy.tenant_id, user.email, list(updates))
    return _to_out(policy)


@router.post("/impact-preview", response_model=ImpactPreviewResult)
async def impact_preview(
    payload: ImpactPreviewRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> ImpactPreviewResult:
    """
    Re-evaluate recent guardrail events against a hypothetical policy.

    Reads up to `window_days` of `guardrail_evaluation` replay events for the
    admin tenant, reconstructs each event's OfferContext from the embedded
    snapshot, and re-runs the Guardrail Engine against the proposed policy.
    Returns per-verdict counts, deltas, revenue/margin impact, and up to 6
    example offers whose verdict would flip.

    Does NOT persist anything. Pure read-only simulation.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=payload.window_days)

    events = (await db.execute(
        select(ReplayEvent).where(
            ReplayEvent.tenant_id == tenant.id,
            ReplayEvent.event_type == EVENT_GUARDRAIL_EVALUATION,
            ReplayEvent.created_at >= cutoff,
        ).order_by(ReplayEvent.created_at.desc())
    )).scalars().all()

    proposed = PolicySnapshot(
        min_margin_percent=float(payload.min_margin_percent),
        max_discount_percent=float(payload.max_discount_percent),
        max_discount_with_approval_percent=float(payload.max_discount_with_approval_percent),
        allowed_regions=tuple(r.upper() for r in payload.allowed_regions),
        currency_allowlist=tuple(c.upper() for c in payload.currency_allowlist),
        min_deal_size_cents=int(payload.min_deal_size_cents),
        max_deal_size_cents=(int(payload.max_deal_size_cents)
                             if payload.max_deal_size_cents is not None else None),
        require_approval_above_cents=int(payload.require_approval_above_cents),
    )
    engine = GuardrailEngine()

    curr = {"pass": 0, "review": 0, "block": 0}
    prop = {"pass": 0, "review": 0, "block": 0}
    revenue_impact = 0.0
    margin_impact = 0.0
    examples: list[ImpactExampleDelta] = []
    evaluated = 0

    # Pull client names for the top-N examples in a single query.
    offer_ids = [e.offer_id for e in events if e.offer_id]
    client_by_offer: dict[str, str] = {}
    if offer_ids:
        sample = offer_ids[:200]
        rows = (await db.execute(
            select(DocumentLog.client, DocumentLog.metadata_json).where(
                DocumentLog.metadata_json.is_not(None)
            )
        )).all()
        for client_name, meta_json in rows:
            try:
                meta = json.loads(meta_json or "{}")
            except json.JSONDecodeError:
                continue
            oid = meta.get("offer_id")
            if oid in sample:
                client_by_offer[oid] = client_name or ""

    for e in events:
        try:
            p = json.loads(e.payload)
        except json.JSONDecodeError:
            continue
        was = p.get("verdict", "pass")
        snap = p.get("offer_context_snapshot")
        if not isinstance(snap, dict):
            # Legacy event without snapshot — count current but skip proposed.
            if was in curr:
                curr[was] += 1
            continue
        line_items = [
            LineItemContext(
                sku=li.get("sku", ""),
                quantity=int(li.get("quantity", 1)),
                unit_price_cents=int(li.get("unit_price_cents", 0)),
                base_price_cents=int(li.get("base_price_cents", 0)),
                min_price_floor_cents=int(li.get("min_price_floor_cents", 0)),
            )
            for li in snap.get("line_items", [])
        ]
        total_cents = int(snap.get("total_cents", 0))
        offer_ctx = OfferContext(
            tenant_id=tenant.id,
            line_items=tuple(line_items),
            total_cents=total_cents,
            currency=str(snap.get("currency", "USD")),
            buyer_region=str(snap.get("region", "US")),
        )
        result = engine.evaluate(offer_ctx, proposed)
        would = result.verdict

        if was in curr:
            curr[was] += 1
        prop[would] += 1
        evaluated += 1

        if would != was:
            dollars = total_cents / 100.0
            # Revenue: flipping pass→block/review is "at risk" revenue, counted negative.
            if was in ("pass", "review") and would == "block":
                revenue_impact -= dollars
            elif was == "block" and would in ("pass", "review"):
                revenue_impact += dollars
            # Margin: sum of (unit - floor) where floors newly hold — approximate.
            for li in line_items:
                margin_impact += (li.unit_price_cents - li.min_price_floor_cents) * li.quantity / 100.0 * 0.01
            if len(examples) < 6 and e.offer_id:
                examples.append(ImpactExampleDelta(
                    offer_id=e.offer_id,
                    client_name=client_by_offer.get(e.offer_id, ""),
                    total_cents=total_cents,
                    was_verdict=was if was in ("pass", "review", "block") else "pass",
                    would_verdict=would,
                    change=f"{was} → {would}",
                ))

    return ImpactPreviewResult(
        window_days=payload.window_days,
        events_evaluated=evaluated,
        current_pass=curr["pass"], current_review=curr["review"], current_block=curr["block"],
        would_pass=prop["pass"], would_review=prop["review"], would_block=prop["block"],
        delta_pass=prop["pass"] - curr["pass"],
        delta_review=prop["review"] - curr["review"],
        delta_block=prop["block"] - curr["block"],
        revenue_impact=round(revenue_impact, 2),
        margin_impact=round(margin_impact, 2),
        examples=examples,
    )


@router.post("/simulate", response_model=SimulateResult)
async def simulate(
    payload: SimulateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> SimulateResult:
    loaded = await load_policy_by_slug(db, tenant.slug)
    if loaded is None:
        raise HTTPException(status_code=500, detail="tenant policy unavailable")

    requested_skus = [li.sku for li in payload.line_items]
    resolved = await resolve_exposed_skus(tenant_slug=tenant.slug, skus=requested_skus)
    unknown = [sku for sku in requested_skus if sku not in resolved]

    # ─── AI preview branch ────────────────────────────────────────────
    if payload.use_ai:
        ai_result = await _simulate_with_ai(
            tenant_id_uuid=tenant.id, tenant_slug=tenant.slug,
            payload=payload, resolved=resolved, loaded=loaded,
        )
        # Re-run through the engine on the AI's final prices so the response
        # is consistent with the non-AI branch's shape.
        items: list[LineItemContext] = []
        resolved_line_items: list[dict] = []
        total_cents = 0
        for p in ai_result["final_lines"]:
            src = resolved.get(p["sku"])
            if src is None:
                continue
            base_cents = dollars_to_cents(src.base_price)
            floor_cents = dollars_to_cents(src.min_price_floor)
            items.append(LineItemContext(
                sku=p["sku"], quantity=p["quantity"],
                unit_price_cents=p["proposed_unit_price_cents"],
                base_price_cents=base_cents, min_price_floor_cents=floor_cents,
            ))
            resolved_line_items.append({
                "sku": p["sku"], "quantity": p["quantity"],
                "unit_price_cents": p["proposed_unit_price_cents"],
                "base_price_cents": base_cents, "min_price_floor_cents": floor_cents,
                "unknown_sku": False,
            })
            total_cents += p["proposed_unit_price_cents"] * p["quantity"]
        offer_context = OfferContext(
            tenant_id=tenant.id, line_items=tuple(items),
            total_cents=total_cents, currency=payload.currency.upper(),
            buyer_region=payload.buyer_region.upper(),
        )
        result = GuardrailEngine().evaluate(offer_context, loaded.snapshot)
        record_evaluation(
            db, tenant_id_uuid=tenant.id, result=result,
            offer_id=None, document_log_id=None,
            principal_id=f"admin:{user.email}",
            extra={"phase": "simulate_ai", "buyer_region": payload.buyer_region},
            simulation=True,
        )
        await db.commit()
        snap = loaded.snapshot
        return SimulateResult(
            verdict=result.verdict,
            check_results=[
                CheckResultOut(
                    name=cr.name, verdict=cr.verdict,
                    reason_internal=cr.reason_internal, reason_external=cr.reason_external,
                    suggested_adjustment=cr.suggested_adjustment,
                )
                for cr in result.check_results
            ],
            policy_snapshot=PolicySnapshotOut(
                min_margin_percent=snap.min_margin_percent,
                max_discount_percent=snap.max_discount_percent,
                max_discount_with_approval_percent=snap.max_discount_with_approval_percent,
                allowed_regions=list(snap.allowed_regions),
                currency_allowlist=list(snap.currency_allowlist),
                min_deal_size_cents=snap.min_deal_size_cents,
                max_deal_size_cents=snap.max_deal_size_cents,
                require_approval_above_cents=snap.require_approval_above_cents,
            ),
            resolved_line_items=resolved_line_items,
            total_cents=total_cents,
            unknown_skus=unknown,
            ai_attempts=ai_result["attempts"],
            ai_fell_back=ai_result["fell_back"],
            ai_backend=ai_result["backend"],
        )

    # Build line item contexts from admin-proposed unit prices.
    items: list[LineItemContext] = []
    resolved_line_items: list[dict] = []
    total_cents = 0
    for li in payload.line_items:
        product = resolved.get(li.sku)
        unit_price_cents = dollars_to_cents(li.unit_price)
        if product is None:
            # Unknown sku → build a best-effort context so engine sees it; mark explicitly.
            items.append(LineItemContext(
                sku=li.sku,
                quantity=li.quantity,
                unit_price_cents=unit_price_cents,
                base_price_cents=0,
                min_price_floor_cents=unit_price_cents + 1,  # forces margin fail
            ))
            resolved_line_items.append({
                "sku": li.sku, "quantity": li.quantity,
                "unit_price_cents": unit_price_cents,
                "base_price_cents": None,
                "min_price_floor_cents": None,
                "unknown_sku": True,
            })
        else:
            base_cents = dollars_to_cents(product.base_price)
            floor_cents = dollars_to_cents(product.min_price_floor)
            items.append(LineItemContext(
                sku=li.sku,
                quantity=li.quantity,
                unit_price_cents=unit_price_cents,
                base_price_cents=base_cents,
                min_price_floor_cents=floor_cents,
            ))
            resolved_line_items.append({
                "sku": li.sku, "quantity": li.quantity,
                "unit_price_cents": unit_price_cents,
                "base_price_cents": base_cents,
                "min_price_floor_cents": floor_cents,
                "unknown_sku": False,
            })
        total_cents += unit_price_cents * li.quantity

    offer_context = OfferContext(
        tenant_id=tenant.id,
        line_items=tuple(items),
        total_cents=total_cents,
        currency=payload.currency.upper(),
        buyer_region=payload.buyer_region.upper(),
    )
    result = GuardrailEngine().evaluate(offer_context, loaded.snapshot)

    record_evaluation(
        db, tenant_id_uuid=tenant.id, result=result,
        offer_id=None, document_log_id=None,
        principal_id=f"admin:{user.email}",
        extra={"phase": "simulate", "buyer_region": payload.buyer_region},
        simulation=True,
    )
    await db.commit()

    snap = loaded.snapshot
    return SimulateResult(
        verdict=result.verdict,
        check_results=[
            CheckResultOut(
                name=cr.name, verdict=cr.verdict,
                reason_internal=cr.reason_internal, reason_external=cr.reason_external,
                suggested_adjustment=cr.suggested_adjustment,
            )
            for cr in result.check_results
        ],
        policy_snapshot=PolicySnapshotOut(
            min_margin_percent=snap.min_margin_percent,
            max_discount_percent=snap.max_discount_percent,
            max_discount_with_approval_percent=snap.max_discount_with_approval_percent,
            allowed_regions=list(snap.allowed_regions),
            currency_allowlist=list(snap.currency_allowlist),
            min_deal_size_cents=snap.min_deal_size_cents,
            max_deal_size_cents=snap.max_deal_size_cents,
            require_approval_above_cents=snap.require_approval_above_cents,
        ),
        resolved_line_items=resolved_line_items,
        total_cents=total_cents,
        unknown_skus=unknown,
    )
