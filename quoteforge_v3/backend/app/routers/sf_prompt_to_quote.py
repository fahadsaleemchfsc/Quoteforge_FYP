"""
Salesforce-native prompt-to-quote flow (Headless 360 LWC entry point).

Two endpoints back the quoteForgePromptBuilder LWC on the Contact record page:

    POST /api/sf/prompt-to-quote    — parse NL prompt → signed offer preview
    POST /api/sf/commit-quote       — verify signature, commit offer, post PDF

The preview endpoint resolves the buyer's free-text request against the
seller's actual agent-exposed catalog (unit prices are authoritative from
the catalog — the prompt cannot introduce prices) and routes the result
through the existing request_quote adapter so guardrails fire uniformly
with the MCP path.

Claude Sonnet handles the parse; a scripted regex fallback covers the case
where ANTHROPIC_API_KEY is missing or the model round-trip fails. Both
produce the same `{sku, quantity}` shape expected by `build_quote_draft`.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session, get_db
from app.core.security import get_current_tenant, get_current_user
from app.gateway.adapters.offer_adapter import (
    InvalidOfferSignatureError,
    OfferExpiredError,
    OfferNotFoundError,
    OfferRejectedError,
    commit_offer,
    ensure_offer_not_expired,
    verify_and_load_offer,
)
from app.gateway.adapters.quote_adapter import (
    GuardrailBlockError,
    QuoteLineRequest,
    QuoteRequestInput,
    UnknownSkusError,
    build_quote_draft,
    load_approval_policy,
)
from app.models.product import Product
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sf", tags=["salesforce-prompt-to-quote"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PromptToQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_text: str = Field(min_length=3, max_length=4000)
    contact_id: str | None = Field(default=None, max_length=32)
    opportunity_id: str | None = Field(default=None, max_length=32)
    # Defensive backward-compat field. Authoritative tenant comes from the
    # JWT (resolved by get_current_tenant). If the caller sends a value, it
    # MUST match the authenticated tenant's slug — mismatch → 403.
    tenant_id: str | None = Field(default=None, max_length=100)


class QuoteLine(BaseModel):
    sku: str
    product_name: str
    quantity: int
    unit_price: float
    line_total: float
    unit: str


class PromptToQuoteResult(BaseModel):
    offer_id: str
    signature: str
    doc_id: str
    client_name: str
    deal_name: str
    region: str
    currency: str
    line_items: list[QuoteLine]
    subtotal: float
    discount: float
    tax: float
    total: float
    total_cents: int
    valid_until: str
    requires_approval: bool
    guardrail_verdict: str  # "pass" | "review" | "block"
    guardrail_reason: str | None = None
    parse_source: str  # "claude" | "scripted"


class CommitQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=64)
    signature: str = Field(min_length=1, max_length=256)
    opportunity_id: str | None = Field(default=None, max_length=32)
    # Defensive backward-compat field — see PromptToQuoteRequest.tenant_id.
    tenant_id: str | None = Field(default=None, max_length=100)


class CommitQuoteResult(BaseModel):
    status: str  # "committed" | "pending_approval" | "expired" | "rejected"
    document_id: str | None = None
    offer_id: str
    total_cents: int | None = None
    currency: str | None = None
    committed_at: str | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# Parsing — Claude primary, scripted fallback
# ---------------------------------------------------------------------------

_CLAUDE_SYSTEM = (
    "You convert free-text B2B buyer requests into structured quote line items. "
    "Return ONLY valid JSON matching this schema:\n"
    '  {"client_name": "...", "deal_name": "...", "region": "US|EU|PK", '
    '"line_items": [{"sku": "...", "quantity": 1}]}\n'
    "Rules:\n"
    "- Only use SKUs from the provided catalog. Do NOT invent SKUs.\n"
    "- Infer quantity from the text; default to 1 if unspecified.\n"
    "- Infer region from country hints (US/USA/United States → US, "
    "Pakistan/PK → PK, Germany/France/UK/EU → EU). Default US.\n"
    "- client_name must be the buyer's company name. If absent, leave empty string.\n"
    "- Do not output prices, currency, discount text, or commentary."
)


async def _parse_with_claude(prompt: str, catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best-effort Claude-powered parse. Returns None on any failure so the
    caller can fall back to the scripted parser."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        catalog_lines = [
            f"- {p['sku']}: {p['name']} ({p.get('category') or 'general'}, {p['currency']})"
            for p in catalog
        ]
        user_msg = (
            f"CATALOG:\n" + "\n".join(catalog_lines) + "\n\n"
            f"PROMPT:\n{prompt}\n\nReturn JSON only."
        )
        resp = await client.messages.create(
            model=settings.BUYER_ROOM_MODEL,
            max_tokens=600,
            system=_CLAUDE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        # Claude sometimes wraps JSON in ```json fences — strip defensively.
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict) or "line_items" not in parsed:
            return None
        return parsed
    except Exception as e:
        logger.info("claude parse failed, falling back to scripted: %s", e)
        return None


def _parse_scripted(prompt: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic regex fallback — SKU keyword match + quantity extraction.

    Matches each catalog entry's SKU and name (case-insensitive) against the
    prompt. For every hit, tries to find a nearby integer quantity; default 1.
    """
    out: dict[str, Any] = {
        "client_name": "",
        "deal_name": "",
        "region": "US",
        "line_items": [],
    }

    # Region
    lower = prompt.lower()
    if re.search(r"\b(pakistan|ppra|lahore|karachi|islamabad|\bpk\b)\b", lower):
        out["region"] = "PK"
    elif re.search(r"\b(germany|france|uk|united kingdom|gdpr|europe|\beu\b)\b", lower):
        out["region"] = "EU"

    # Client — "for XYZ" or "quote XYZ"
    m = re.search(
        r"(?:proposal|quote|deal|for)\s+(?:for\s+)?([A-Z][A-Za-z0-9&.\- ]{2,60}?)"
        r"(?=\s+(?:in|they|needs?|wants?|requires?|is|are)|[.,]|$)",
        prompt,
    )
    if m:
        out["client_name"] = m.group(1).strip().rstrip(",. ")

    # SKU / name matching — each catalog entry at most once
    seen: set[str] = set()
    for p in catalog:
        sku = p["sku"]
        name = p["name"]
        pattern = re.compile(
            rf"\b({re.escape(sku)}|{re.escape(name)})\b", re.IGNORECASE,
        )
        match = pattern.search(prompt)
        if not match or sku in seen:
            continue
        seen.add(sku)

        # Quantity: look within 30 chars before the match for "N units/of/x"
        start = max(0, match.start() - 30)
        window = prompt[start: match.end()]
        qty_match = re.search(r"(\d+)\s*(?:x|units?|licenses?|seats?|of)?\s*$", window)
        qty = int(qty_match.group(1)) if qty_match else 1
        qty = max(1, min(qty, 10000))

        out["line_items"].append({"sku": sku, "quantity": qty})

    return out


# ---------------------------------------------------------------------------
# Endpoint: preview
# ---------------------------------------------------------------------------

@router.post("/prompt-to-quote", response_model=PromptToQuoteResult)
async def prompt_to_quote(
    req: PromptToQuoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Parse an NL prompt → signed offer preview (no commit yet).

    The LWC calls this to render a line-item table + guardrail verdict.
    The user clicks Approve → LWC calls /api/sf/commit-quote with
    (offer_id, signature) to finalize.
    """
    # Defensive: if the caller sent a tenant_id in the body, it must match
    # the authenticated tenant. The JWT is the authoritative source.
    if req.tenant_id and req.tenant_id != tenant.slug:
        raise HTTPException(
            403, "tenant_id in request body does not match authenticated tenant",
        )

    cat_stmt = select(Product).where(
        Product.tenant_id == tenant.id, Product.agent_exposed.is_(True),
    )
    products = (await db.execute(cat_stmt)).scalars().all()
    if not products:
        raise HTTPException(
            409,
            "no agent-exposed products in catalog — "
            "expose at least one product before using prompt-to-quote",
        )
    catalog = [
        {
            "sku": p.sku, "name": p.name, "category": p.category,
            "currency": p.currency,
        }
        for p in products
    ]

    parsed = await _parse_with_claude(req.prompt_text, catalog)
    parse_source = "claude" if parsed else "scripted"
    if parsed is None:
        parsed = _parse_scripted(req.prompt_text, catalog)

    line_items = parsed.get("line_items") or []
    if not line_items:
        raise HTTPException(
            422,
            "could not extract any products from the prompt. "
            "Mention at least one SKU or product name from the catalog.",
        )

    client_name = (parsed.get("client_name") or "").strip() or "Unnamed Buyer"
    deal_name = (parsed.get("deal_name") or "").strip() or f"{client_name} — SF Prompt"
    region = (parsed.get("region") or "US").upper()[:3] or "US"

    adapter_input = QuoteRequestInput(
        tenant_id=tenant.slug,
        principal_id=f"sf_prompt:{current_user.email}",
        client_name=client_name,
        deal_name=deal_name,
        region=region,
        contact_email="",
        line_items=tuple(
            QuoteLineRequest(sku=li["sku"], quantity=int(li.get("quantity", 1)))
            for li in line_items
            if li.get("sku")
        ),
    )
    if not adapter_input.line_items:
        raise HTTPException(422, "parsed line items had no valid SKUs")

    try:
        result = await build_quote_draft(adapter_input)
    except UnknownSkusError as e:
        raise HTTPException(
            400,
            f"SKUs not agent-exposed or unknown: {', '.join(e.skus)}. "
            "Check the Products page and toggle 'Expose to agents'.",
        ) from e
    except GuardrailBlockError as e:
        external = e.result.external_payload()
        return PromptToQuoteResult(
            offer_id="",
            signature="",
            doc_id="",
            client_name=client_name,
            deal_name=deal_name,
            region=region,
            currency="USD",
            line_items=[],
            subtotal=0.0,
            discount=0.0,
            tax=0.0,
            total=0.0,
            total_cents=0,
            valid_until="",
            requires_approval=True,
            guardrail_verdict="block",
            guardrail_reason=external.get("reason"),
            parse_source=parse_source,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    offer = result["offer"]
    pricing = offer["pricing"]

    verdict = "review" if result.get("requires_approval") else "pass"

    return PromptToQuoteResult(
        offer_id=offer["offer_id"],
        signature=result["signature"],
        doc_id=offer["doc_id"],
        client_name=offer["client_name"],
        deal_name=offer["deal_name"],
        region=offer["region"],
        currency=pricing["currency"],
        line_items=[
            QuoteLine(
                sku=li["sku"],
                product_name=li["product_name"],
                quantity=li["quantity"],
                unit_price=li["unit_price"],
                line_total=li["line_total"],
                unit=li["unit"],
            )
            for li in offer["line_items"]
        ],
        subtotal=pricing["subtotal"],
        discount=pricing["discount"],
        tax=pricing["tax"],
        total=pricing["total"],
        total_cents=pricing["total_cents"],
        valid_until=offer["valid_until"],
        requires_approval=result["requires_approval"],
        guardrail_verdict=verdict,
        guardrail_reason=None,
        parse_source=parse_source,
    )


# ---------------------------------------------------------------------------
# Endpoint: commit
# ---------------------------------------------------------------------------

@router.post("/commit-quote", response_model=CommitQuoteResult)
async def commit_quote(
    req: CommitQuoteRequest,
    tenant: Tenant = Depends(get_current_tenant),
):
    """Verify signature + commit the offer drafted by /sf/prompt-to-quote.

    Mirrors the accept_offer MCP tool's success-path logic, scoped to the
    Salesforce LWC flow. Tenant is resolved from the JWT; an optional
    `tenant_id` in the request body is honored only if it matches.
    """
    # Defensive: if the caller sent a tenant_id in the body, it must match
    # the authenticated tenant. The JWT is the authoritative source.
    if req.tenant_id and req.tenant_id != tenant.slug:
        raise HTTPException(
            403, "tenant_id in request body does not match authenticated tenant",
        )

    async with async_session() as db:
        try:
            fetched = await verify_and_load_offer(
                db,
                tenant_slug=tenant.slug,
                offer_id=req.offer_id,
                signature=req.signature,
            )
        except OfferNotFoundError:
            raise HTTPException(404, f"offer not found: {req.offer_id}")
        except InvalidOfferSignatureError:
            raise HTTPException(400, "invalid offer signature — tampered or stale")

        policy = await load_approval_policy(db, tenant.slug)
        if policy is None:
            raise HTTPException(500, "tenant config unavailable")

        doc_status = fetched.document_log.status
        if doc_status == "committed":
            # Idempotent replay.
            try:
                result = await commit_offer(
                    db, fetched=fetched, tenant_id_uuid=policy.tenant_id,
                    buyer_agent_id=f"sf_prompt:commit", source="agent_gateway",
                    buyer_reference=req.opportunity_id,
                )
            except OfferRejectedError:
                raise HTTPException(409, "offer was rejected by the seller")
            await db.commit()
            return CommitQuoteResult(
                status="committed",
                document_id=result.document_id,
                offer_id=result.offer_id,
                total_cents=result.total_cents,
                currency=result.currency,
                committed_at=result.committed_at.isoformat(),
                message="already committed (idempotent replay)",
            )

        if doc_status == "rejected":
            return CommitQuoteResult(
                status="rejected",
                offer_id=req.offer_id,
                message="this offer was rejected by the seller — request a new quote",
            )

        try:
            ensure_offer_not_expired(fetched)
        except OfferExpiredError:
            return CommitQuoteResult(
                status="expired",
                offer_id=req.offer_id,
                message="offer validity window passed — request a new quote",
            )

        total_cents = int(fetched.offer_payload["pricing"]["total_cents"])
        currency = fetched.offer_payload["pricing"]["currency"]

        # If the offer was drafted as 'pending_approval' (approval threshold
        # or review verdict at quote time), don't auto-commit here — the LWC
        # should show a message telling the rep to use the Approvals queue.
        if doc_status == "pending_approval":
            return CommitQuoteResult(
                status="pending_approval",
                offer_id=req.offer_id,
                total_cents=total_cents,
                currency=currency,
                message="offer is pending human approval — see Approvals",
            )

        try:
            result = await commit_offer(
                db, fetched=fetched, tenant_id_uuid=policy.tenant_id,
                buyer_agent_id=f"sf_prompt:commit", source="agent_gateway",
                buyer_reference=req.opportunity_id,
            )
        except OfferRejectedError:
            raise HTTPException(409, "offer was rejected by the seller")
        await db.commit()
        return CommitQuoteResult(
            status="committed",
            document_id=result.document_id,
            offer_id=result.offer_id,
            total_cents=result.total_cents,
            currency=result.currency,
            committed_at=result.committed_at.isoformat(),
        )
