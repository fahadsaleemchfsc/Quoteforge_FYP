"""
Quote adapter — the thin seam between MCP tools and existing services.

Wraps:
  - app.gateway.adapters.product_adapter.resolve_exposed_skus (catalog lookup)
  - app.services.pricing_engine.apply_pricing_rules (discount + tax math only)
  - app.models.document_log.DocumentLog (persists quote drafts)
  - app.models.audit_log.AuditLog (Replay Layer entries)

Produces a signed, stateless offer. The signature lets accept_offer verify an
offer without trusting client-held fields — if any byte of the offer payload
changed, the HMAC no longer matches.

Signing scheme (Phase 1): HMAC-SHA256 over a canonical JSON serialization of
the offer, keyed by settings.SECRET_KEY. Phase 3 upgrades to RS256 with a
rotating keypair published at /.well-known/jwks.json.

Note: this adapter deliberately does NOT include any compliance / legal fields
in the offer payload. Regional legal clause injection is out of scope per the
updated Guardrail Engine charter (margin floor, discount cap, approval
threshold, allowed regions — nothing more).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.gateway.adapters.doc_id import next_doc_id
from app.gateway.adapters.product_adapter import (
    ResolvedExposedProduct,
    resolve_exposed_skus,
)
from app.gateway.guardrails import GuardrailEngine
from app.gateway.guardrails.builder import from_resolved_lines
from app.gateway.guardrails.engine import EngineResult, LineItemContext, OfferContext
from app.gateway.guardrails.policy_loader import LoadedPolicy, load_policy_by_slug
from app.gateway.guardrails.replay import record_evaluation, record_negotiation_attempt
from app.gateway.money import cents_to_dollars, dollars_to_cents
from app.gateway.negotiation import NegotiationContext, NegotiationService
from app.gateway.negotiation.context import (
    NegotiationAttempt,
    NegotiationLine,
    PolicyHints,
)
from app.models.audit_log import AuditLog
from app.models.document_log import DocumentLog
from app.models.replay_event import EVENT_GUARDRAIL_EVALUATION, ReplayEvent
from app.models.tenant import Tenant
from app.models.tenant_config import (
    DEFAULT_APPROVAL_THRESHOLD_CENTS,
    NEGOTIATION_MODE_AI_FIRST,
    NEGOTIATION_MODE_DETERMINISTIC,
    TenantConfig,
)
from app.services.pricing_engine import apply_pricing_rules

logger = logging.getLogger(__name__)

# How long a quote offer stays valid for acceptance.
OFFER_VALIDITY_DAYS = 30


@dataclass(frozen=True)
class QuoteLineRequest:
    sku: str
    quantity: int


@dataclass(frozen=True)
class QuoteRequestInput:
    tenant_id: str
    principal_id: str
    client_name: str
    deal_name: str
    region: str
    contact_email: str
    line_items: tuple[QuoteLineRequest, ...]


@dataclass(frozen=True)
class FetchedOffer:
    """The stored shape we need for accept_offer — the live DocumentLog row,
    the full offer payload as originally signed, and the stored signature."""
    document_log: DocumentLog
    offer_payload: dict[str, Any]
    signature: str
    tenant_slug: str


class UnknownSkusError(Exception):
    """Raised when at least one requested SKU is missing or not agent_exposed."""

    def __init__(self, skus: list[str]) -> None:
        super().__init__(f"skus not available for agent purchase: {skus}")
        self.skus = skus


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sign(payload: dict[str, Any]) -> str:
    mac = hmac.new(settings.SECRET_KEY.encode("utf-8"), _canonical(payload), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).rstrip(b"=").decode("ascii")


def sign_offer(payload: dict[str, Any]) -> str:
    """Public wrapper exposing _sign for other adapters that need re-signing."""
    return _sign(payload)


def verify_offer_signature(payload: dict[str, Any], signature: str) -> bool:
    return hmac.compare_digest(_sign(payload), signature)


@dataclass(frozen=True)
class ApprovalPolicy:
    """Backwards-compatible shape consumed by accept_offer.

    Values are now sourced from GuardrailPolicy.require_approval_above_cents
    plus TenantConfig.auto_commit_enabled. Keep the dataclass so existing
    callers don't churn.
    """
    tenant_id: str                      # Tenant.id (UUID), not slug
    approval_threshold_cents: int
    auto_commit_enabled: bool

    def requires_approval(self, total_cents: int) -> bool:
        if not self.auto_commit_enabled:
            return True
        return total_cents >= self.approval_threshold_cents


async def load_approval_policy(db: AsyncSession, tenant_slug: str) -> ApprovalPolicy | None:
    """Resolve slug → GuardrailPolicy + TenantConfig. Returns None if tenant missing."""
    loaded = await load_policy_by_slug(db, tenant_slug)
    if loaded is None:
        return None
    return ApprovalPolicy(
        tenant_id=loaded.tenant_id_uuid,
        approval_threshold_cents=loaded.snapshot.require_approval_above_cents,
        auto_commit_enabled=loaded.auto_commit_enabled,
    )


class GuardrailBlockError(Exception):
    """Raised when the guardrail engine refuses to construct the offer."""

    def __init__(self, result: EngineResult) -> None:
        super().__init__("guardrail block")
        self.result = result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Doc-ID generation is now an atomic per-tenant counter; see doc_id.next_doc_id.
# The previous implementation counted DocumentLog rows and emitted
# f"DOC-{count+1}", which raced under concurrent request_quote calls and
# collided on document_logs.doc_id UNIQUE.


def _price_line(product: ResolvedExposedProduct, quantity: int) -> dict[str, Any]:
    unit_price = product.base_price
    line_total = unit_price * Decimal(quantity)
    return {
        "sku": product.sku,
        "product_id": product.id,
        "product_name": product.name,
        "description": product.description,
        "quantity": quantity,
        "unit_price": float(unit_price.quantize(Decimal("0.01"))),
        "line_total": float(line_total.quantize(Decimal("0.01"))),
        "unit": product.unit,
    }


# ---------------------------------------------------------------------------
# Main entrypoint used by the MCP tool
# ---------------------------------------------------------------------------

async def build_quote_draft(req: QuoteRequestInput) -> dict[str, Any]:
    """
    Validate SKUs → deterministically price → persist draft → return signed offer.

    Buyer agents specify `sku` and `quantity`; unit_price is authoritative from
    the catalog. This closes the obvious attack where a buyer agent sends a
    $0.01 unit_price. Any SKU that is not agent_exposed for the tenant causes
    the whole request to fail with UnknownSkusError — partial success would
    reveal the catalog shape to scanners.

    Intentionally skips AI section generation. Buyer agents want numbers;
    human-readable narrative is produced on demand by the Dual Output Renderer
    (Module 4) against the same stored draft.
    """
    if not req.line_items:
        raise ValueError("at least one line item is required")
    if not req.client_name:
        raise ValueError("client_name is required")

    requested_skus = [li.sku for li in req.line_items]

    resolved = await resolve_exposed_skus(tenant_slug=req.tenant_id, skus=requested_skus)
    missing = [sku for sku in requested_skus if sku not in resolved]
    if missing:
        raise UnknownSkusError(missing)

    # Currency coherence: single quote cannot mix currencies. Buyer agents
    # should request per-currency quotes if they need both.
    currencies = {resolved[sku].currency for sku in requested_skus}
    if len(currencies) > 1:
        raise ValueError(f"cannot mix currencies in one quote: {sorted(currencies)}")
    currency = currencies.pop()

    async with async_session() as db:
        loaded = await load_policy_by_slug(db, req.tenant_id)
        if loaded is None:
            raise ValueError(f"unknown tenant: {req.tenant_id}")

        # ─── Mode dispatch ─────────────────────────────────────────────
        # AI-first: NegotiationService proposes unit prices, guardrails gate
        # every attempt, falls back to base prices if the retry budget is blown.
        # Deterministic: unit prices = base_price, legacy discount/tax rules run.
        tenant_mode = await _load_negotiation_mode(db, loaded.tenant_id_uuid)
        priced_items: list[dict[str, Any]]
        pricing: dict[str, Any]
        negotiation_attempts: tuple[NegotiationAttempt, ...] = ()
        ai_fell_back = False
        ai_backend_name: str | None = None
        offer_context_for_replay: OfferContext | None = None
        engine_result: EngineResult

        offer_id = f"ofr_{uuid.uuid4().hex[:20]}"

        if tenant_mode == NEGOTIATION_MODE_AI_FIRST:
            priced_items, pricing, negotiation_attempts, ai_fell_back, \
                ai_backend_name, engine_result, offer_context_for_replay = \
                await _run_ai_first_pricing(
                    db=db,
                    req=req,
                    resolved=resolved,
                    loaded=loaded,
                    currency=currency,
                    offer_id=offer_id,
                )
        else:
            priced_items, pricing, engine_result, offer_context_for_replay = \
                await _run_deterministic_pricing(
                    db=db,
                    req=req,
                    resolved=resolved,
                    loaded=loaded,
                    currency=currency,
                )

        if engine_result.verdict == "block":
            record_evaluation(
                db,
                tenant_id_uuid=loaded.tenant_id_uuid,
                result=engine_result,
                offer_id=None,
                document_log_id=None,
                principal_id=req.principal_id,
                extra={"phase": "request_quote", "client_name": req.client_name,
                       "negotiation_mode": tenant_mode},
            )
            await db.commit()
            raise GuardrailBlockError(engine_result)

        deal_amount = Decimal(str(pricing["subtotal"]))

        doc_id = await next_doc_id(db, loaded.tenant_id_uuid)
        now = datetime.now(timezone.utc)
        valid_until = now + timedelta(days=OFFER_VALIDITY_DAYS)
        total_cents = dollars_to_cents(pricing["total"])

        # NOTE: no compliance block — that concern is explicitly out of scope.
        offer_payload: dict[str, Any] = {
            "offer_id": offer_id,
            "doc_id": doc_id,
            "tenant_id": req.tenant_id,
            "issued_at": now.isoformat(),
            "valid_until": valid_until.isoformat(),
            "client_name": req.client_name,
            "deal_name": req.deal_name,
            "region": req.region,
            "contact_email": req.contact_email,
            "line_items": priced_items,
            "pricing": {
                "subtotal": pricing["subtotal"],
                "discount": pricing["discount"],
                "discount_details": pricing["discount_details"],
                "tax": pricing["tax"],
                "tax_details": pricing["tax_details"],
                "total": pricing["total"],
                "total_cents": total_cents,
                "currency": currency,
            },
        }
        signature = _sign(offer_payload)

        # Engine verdict (review vs pass) drives requires_approval — combined
        # with auto_commit_enabled (kill-switch) below.
        guardrail_requires_approval = engine_result.verdict == "review"
        requires_approval = guardrail_requires_approval or not loaded.auto_commit_enabled

        metadata = {
            "tenant_slug": req.tenant_id,
            "mcp_principal": req.principal_id,
            "offer_id": offer_id,
            "offer_signature": signature,
            "offer_payload": offer_payload,         # full payload for verify + replay
            "source": "agent_gateway",
            "product_ids": [it["product_id"] for it in priced_items],
        }

        doc = DocumentLog(
            doc_id=doc_id,
            deal_id="",
            client=req.client_name,
            deal_name=req.deal_name,
            type="Quote",
            format="JSON",
            status="draft",
            delivery_status="pending",
            file_path="",
            amount=pricing["total"],
            generation_time=0.0,
            valid_until=valid_until,
            metadata_json=json.dumps(metadata),
            user_id=None,
            user_name=f"mcp:{req.principal_id}",
        )
        db.add(doc)

        db.add(AuditLog(
            user_id=None,
            user_name=f"mcp:{req.principal_id}",
            action="quote_requested",
            entity_type="offer",
            entity_id=offer_id,
            details=(
                f"tenant={req.tenant_id} client={req.client_name} "
                f"total={pricing['total']:.2f} {currency} via=agent_gateway "
                f"mode={tenant_mode} "
                f"verdict={engine_result.verdict} requires_approval={requires_approval}"
                + (f" fell_back=true" if ai_fell_back else "")
            ),
        ))

        # Record the engine's pass/review verdict to the Replay Layer too.
        record_evaluation(
            db,
            tenant_id_uuid=loaded.tenant_id_uuid,
            result=engine_result,
            offer_id=offer_id,
            document_log_id=None,              # doc row not yet flushed — link on re-eval if needed
            principal_id=req.principal_id,
            extra={"phase": "request_quote", "client_name": req.client_name,
                   "negotiation_mode": tenant_mode},
        )

        # Record each AI attempt to the Replay Layer, scoped to this offer_id.
        for attempt in negotiation_attempts:
            record_negotiation_attempt(
                db,
                tenant_id_uuid=loaded.tenant_id_uuid,
                offer_id=offer_id,
                principal_id=req.principal_id,
                attempt_number=attempt.attempt_number,
                backend=attempt.backend,
                verdict=attempt.verdict,
                blocking_check_names=attempt.blocking_check_names,
                latency_ms=attempt.latency_ms,
                proposed_lines=(
                    [{"sku": l.sku, "quantity": l.quantity,
                      "proposed_unit_price_cents": l.proposed_unit_price_cents}
                     for l in attempt.proposed.lines]
                    if attempt.proposed else None
                ),
                rationale=attempt.proposed.rationale if attempt.proposed else None,
                confidence=attempt.proposed.confidence if attempt.proposed else None,
                raw_model_output=attempt.proposed.raw_model_output if attempt.proposed else None,
                error=attempt.error,
                fell_back=ai_fell_back and attempt is negotiation_attempts[-1],
            )

        await db.commit()

        logger.info(
            "quote drafted offer=%s doc=%s tenant=%s principal=%s total=%.2f %s verdict=%s approval=%s",
            offer_id, doc_id, req.tenant_id, req.principal_id,
            pricing["total"], currency, engine_result.verdict, requires_approval,
        )

    return {
        "offer": offer_payload,
        "signature": signature,
        "signature_algorithm": "HS256",
        "total_cents": total_cents,
        "requires_approval": requires_approval,
        "approval_threshold_cents": loaded.snapshot.require_approval_above_cents,
        "negotiation_mode": tenant_mode,
        "negotiation_attempts": len(negotiation_attempts),
        "fell_back_to_deterministic": ai_fell_back,
        "model_backend": ai_backend_name,
    }


async def _load_negotiation_mode(db: AsyncSession, tenant_id_uuid: str) -> str:
    cfg = (
        await db.execute(
            select(TenantConfig.negotiation_mode).where(TenantConfig.tenant_id == tenant_id_uuid)
        )
    ).scalar_one_or_none()
    return cfg or NEGOTIATION_MODE_DETERMINISTIC


def _policy_hints_from_snapshot(snapshot) -> PolicyHints:
    return PolicyHints(
        min_margin_percent=snapshot.min_margin_percent,
        max_discount_percent=snapshot.max_discount_percent,
        max_discount_with_approval_percent=snapshot.max_discount_with_approval_percent,
        allowed_regions=snapshot.allowed_regions,
        currency_allowlist=snapshot.currency_allowlist,
    )


async def _run_deterministic_pricing(
    *,
    db: AsyncSession,
    req: QuoteRequestInput,
    resolved: dict[str, ResolvedExposedProduct],
    loaded: LoadedPolicy,
    currency: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], EngineResult, OfferContext]:
    """Legacy path: unit prices from the catalog, apply_pricing_rules for tax+discount."""
    priced_items = [_price_line(resolved[li.sku], li.quantity) for li in req.line_items]
    deal_amount = sum(Decimal(str(it["line_total"])) for it in priced_items)
    pricing = await apply_pricing_rules(
        db=db,
        deal_amount=float(deal_amount),
        region=req.region or "US",
        line_items=[
            {"quantity": it["quantity"], "unit_price": it["unit_price"]}
            for it in priced_items
        ],
    )
    total_cents = dollars_to_cents(pricing["total"])
    offer_context = from_resolved_lines(
        tenant_id_uuid=loaded.tenant_id_uuid,
        buyer_region=req.region or "US",
        currency=currency,
        resolved=resolved,
        line_order=[(li.sku, li.quantity) for li in req.line_items],
        total_cents=total_cents,
    )
    engine_result = GuardrailEngine().evaluate(offer_context, loaded.snapshot)
    return priced_items, pricing, engine_result, offer_context


async def _run_ai_first_pricing(
    *,
    db: AsyncSession,
    req: QuoteRequestInput,
    resolved: dict[str, ResolvedExposedProduct],
    loaded: LoadedPolicy,
    currency: str,
    offer_id: str,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    tuple[NegotiationAttempt, ...],
    bool,
    str,
    EngineResult,
    OfferContext,
]:
    """AI-first path: NegotiationService proposes → guardrail validates → return.

    Tax is intentionally reported as $0 in this path. The AI's proposal is
    already a discounted price; the legacy apply_pricing_rules would
    double-discount if re-applied. Tax computation lands in Module 4 (Dual
    Output Renderer) where it belongs — with the region-aware renderer, not
    inline in the negotiation loop.
    """
    nc = NegotiationContext(
        tenant_id=loaded.tenant_id_uuid,
        tenant_slug=req.tenant_id,
        buyer_region=req.region or "US",
        buyer_client_name=req.client_name,
        buyer_deal_name=req.deal_name or "",
        buyer_metadata={"principal_id": req.principal_id},
        lines=tuple(
            NegotiationLine(
                sku=li.sku,
                quantity=li.quantity,
                base_price_cents=dollars_to_cents(resolved[li.sku].base_price),
                min_price_floor_cents=dollars_to_cents(resolved[li.sku].min_price_floor),
                product_name=resolved[li.sku].name,
                description=resolved[li.sku].description,
            )
            for li in req.line_items
        ),
        similar_deals=(),                             # RAG hook — Module 5 populates this
        policy_hints=_policy_hints_from_snapshot(loaded.snapshot),
    )

    service = NegotiationService()
    validated = await service.propose_and_validate(
        context=nc, policy=loaded.snapshot, currency=currency,
    )

    # Build the priced_items shape the rest of the pipeline expects from the
    # validated proposal. Line_total in dollars.
    priced_items: list[dict[str, Any]] = []
    subtotal_cents = 0
    total_discount_cents = 0
    for proposed in validated.final_lines:
        src = resolved[proposed.sku]
        unit_dollars = cents_to_dollars(proposed.proposed_unit_price_cents)
        line_total_cents = proposed.proposed_unit_price_cents * proposed.quantity
        subtotal_cents += line_total_cents
        base_cents = dollars_to_cents(src.base_price)
        total_discount_cents += (base_cents - proposed.proposed_unit_price_cents) * proposed.quantity
        priced_items.append({
            "sku": proposed.sku,
            "product_id": src.id,
            "product_name": src.name,
            "description": src.description,
            "quantity": proposed.quantity,
            "unit_price": round(unit_dollars, 2),
            "line_total": round(line_total_cents / 100, 2),
            "unit": src.unit,
        })

    pricing = {
        "subtotal": round(subtotal_cents / 100, 2),
        "discount": round(max(0, total_discount_cents) / 100, 2),
        "discount_details": [{
            "rule": "negotiation_ai",
            "percentage": f"{(total_discount_cents / max(1, subtotal_cents + total_discount_cents)) * 100:.1f}%",
            "amount": round(max(0, total_discount_cents) / 100, 2),
        }] if total_discount_cents > 0 else [],
        "tax": 0.0,
        "tax_details": [],
        "total": round(subtotal_cents / 100, 2),
    }

    # Rebuild an OfferContext that reflects AI-proposed unit_prices (not the
    # catalog baseline). NegotiationService evaluated this already; we repeat
    # it here so the return value mirrors what gets signed into the offer.
    ai_line_items = tuple(
        LineItemContext(
            sku=p.sku, quantity=p.quantity,
            unit_price_cents=p.proposed_unit_price_cents,
            base_price_cents=dollars_to_cents(resolved[p.sku].base_price),
            min_price_floor_cents=dollars_to_cents(resolved[p.sku].min_price_floor),
        )
        for p in validated.final_lines
    )
    offer_context_ai = OfferContext(
        tenant_id=loaded.tenant_id_uuid,
        line_items=ai_line_items,
        total_cents=subtotal_cents,
        currency=currency,
        buyer_region=req.region or "US",
    )
    engine_result = GuardrailEngine().evaluate(offer_context_ai, loaded.snapshot)

    return (
        priced_items,
        pricing,
        validated.attempts,
        validated.fell_back,
        validated.backend_name,
        engine_result,
        offer_context_ai,
    )


async def fetch_offer_by_id(db: AsyncSession, tenant_slug: str, offer_id: str) -> FetchedOffer | None:
    """Look up the persisted draft by offer_id, scoped to the calling tenant.

    Uses LIKE on metadata_json as a lookup shortcut while we're on SQLite.
    This is N=1 in practice because offer_id is a random UUID-derived string.
    On Postgres we'd replace this with a JSONB @> containment lookup and/or a
    dedicated `offers` table with a proper index — TODO: Phase 2.
    """
    result = await db.execute(
        select(DocumentLog).where(DocumentLog.metadata_json.like(f'%"offer_id": "{offer_id}"%'))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        return None
    try:
        meta = json.loads(doc.metadata_json or "{}")
    except json.JSONDecodeError:
        return None
    if meta.get("tenant_slug") != tenant_slug:
        return None
    payload = meta.get("offer_payload")
    signature = meta.get("offer_signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return None
    return FetchedOffer(
        document_log=doc,
        offer_payload=payload,
        signature=signature,
        tenant_slug=tenant_slug,
    )
