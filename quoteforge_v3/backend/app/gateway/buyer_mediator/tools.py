"""
Tool handlers for the buyer-room mediator.

Claude's tool calls land here. Each handler wraps an existing internal
adapter — we deliberately don't go through MCP/HTTP because this is an
in-process call from a trusted server-side orchestrator, not a buyer agent.

The Guardrail Engine still runs. The handler distinction:
  - MCP path: external agent, full auth + rate limit + tenant check
  - Mediator path: internal, tenant already resolved from the share token,
    no rate limit (we control the caller), same guardrails

Internal fields (signatures, floor prices, policy numerics) are never
returned from these handlers to Claude. Claude only sees what a buyer
agent would see — so even if the model hallucinates a reveal, there's
nothing sensitive in scope to reveal.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.gateway.adapters.product_adapter import (
    AgentProductFilters,
    list_products_for_agent,
)
from app.gateway.adapters.offer_adapter import (
    InvalidOfferSignatureError,
    OfferExpiredError,
    OfferNotFoundError,
    OfferRejectedError,
    commit_offer,
    ensure_offer_not_expired,
    queue_for_approval,
    re_evaluate_against_policy,
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
from app.gateway.buyer_mediator.session import BuyerSession, OfferState
from app.core.database import async_session
import time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schema — fed to Claude's `tools` parameter
# ---------------------------------------------------------------------------

TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "fetch_catalog",
        "description": (
            "List the seller's agent-accessible products. Call this once near "
            "the start of a conversation so you know what you're allowed to "
            "quote. Returns SKU, name, description, category, base price, unit."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "request_quote",
        "description": (
            "Request a priced quote for specific SKUs and quantities. The "
            "seller's guardrails validate the proposal; you will either get "
            "an offer back with pricing + acceptance gating, or a rejection "
            "explaining which limit was hit. Always run this before promising "
            "the buyer a price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "line_items": {
                    "type": "array",
                    "description": "SKU + quantity pairs.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1},
                        },
                        "required": ["sku", "quantity"],
                    },
                    "minItems": 1,
                },
                "client_name": {
                    "type": "string",
                    "description": "Buyer's company name if the buyer has shared it, else 'Guest'.",
                },
                "deal_name": {
                    "type": "string",
                    "description": "Short label for this deal, e.g. 'Q2 Renewal'.",
                },
                "region": {
                    "type": "string",
                    "enum": ["US", "EU", "APAC", "UK"],
                    "description": "Buyer's region; affects tax and which rules fire.",
                },
            },
            "required": ["line_items"],
        },
    },
    {
        "name": "accept_current_offer",
        "description": (
            "Commit the most recent offer on this session. Only call after "
            "the buyer has explicitly said yes to the specific numbers. If "
            "there is no current offer, this fails — call request_quote first."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ---------------------------------------------------------------------------
# Handlers — return plain JSON dicts Claude can read back as tool_result
# ---------------------------------------------------------------------------

async def handle_fetch_catalog(session: BuyerSession) -> dict[str, Any]:
    principal = f"buyer-room:{session.session_id}"
    products = await list_products_for_agent(
        tenant_slug=session.tenant_slug,
        principal_id=principal,
        filters=AgentProductFilters(limit=50),
    )
    return {"products": products, "count": len(products)}


async def handle_request_quote(
    session: BuyerSession,
    line_items: list[dict[str, Any]],
    client_name: str = "Guest",
    deal_name: str = "",
    region: str = "US",
) -> dict[str, Any]:
    principal = f"buyer-room:{session.session_id}"
    adapter_input = QuoteRequestInput(
        tenant_id=session.tenant_slug,
        principal_id=principal,
        client_name=(client_name or "Guest")[:200],
        deal_name=(deal_name or "")[:200],
        region=region or "US",
        contact_email="",
        line_items=tuple(
            QuoteLineRequest(sku=str(li.get("sku", "")), quantity=int(li.get("quantity", 0)))
            for li in line_items
            if li.get("sku") and int(li.get("quantity", 0)) > 0
        ),
    )

    try:
        result = await build_quote_draft(adapter_input)
    except UnknownSkusError as e:
        return {
            "status": "rejected",
            "reason": "unknown_or_unavailable_skus",
            "unavailable_skus": e.skus,
            "message": (
                "Some of those SKUs aren't available for this buyer path. "
                "Tell the buyer which ones and suggest looking at the catalog."
            ),
        }
    except GuardrailBlockError as e:
        external = e.result.external_payload()
        return {
            "status": "rejected",
            "reason": "guardrail_block",
            "external_reason": external.get("reason"),
            "suggested_adjustment": external.get("suggested_adjustment"),
            "message": (
                "The seller's pricing rules won't let this quote through. "
                "The suggested_adjustment field shows what prices would work; "
                "explain that to the buyer without revealing internal policy."
            ),
        }
    except ValueError as e:
        return {"status": "rejected", "reason": "invalid_input", "message": str(e)}

    # Persist signed offer into the session so accept_current_offer can commit.
    offer_payload = result["offer"]
    session.offer = OfferState(
        offer_id=offer_payload["offer_id"],
        signature=result["signature"],
        payload=offer_payload,
        requires_approval=bool(result["requires_approval"]),
        created_at=time.monotonic(),
    )
    session.touch()

    # Return the buyer-visible subset — NO signature, NO internal fields.
    return {
        "status": "issued",
        "offer": {
            "offer_id": offer_payload["offer_id"],
            "valid_until": offer_payload["valid_until"],
            "client_name": offer_payload["client_name"],
            "line_items": offer_payload["line_items"],
            "pricing": offer_payload["pricing"],
            "requires_approval": bool(result["requires_approval"]),
        },
    }


async def handle_accept_current_offer(session: BuyerSession) -> dict[str, Any]:
    if session.offer is None:
        return {
            "status": "error",
            "reason": "no_current_offer",
            "message": "Ask the buyer what they want to buy, then call request_quote first.",
        }

    principal = f"buyer-room:{session.session_id}"
    async with async_session() as db:
        try:
            fetched = await verify_and_load_offer(
                db,
                tenant_slug=session.tenant_slug,
                offer_id=session.offer.offer_id,
                signature=session.offer.signature,
            )
        except OfferNotFoundError:
            return {"status": "error", "reason": "offer_not_found"}
        except InvalidOfferSignatureError:
            return {"status": "error", "reason": "signature_invalid"}

        policy = await load_approval_policy(db, session.tenant_slug)
        if policy is None:
            return {"status": "error", "reason": "tenant_config_unavailable"}

        try:
            ensure_offer_not_expired(fetched)
        except OfferExpiredError:
            return {"status": "error", "reason": "offer_expired"}

        # Re-evaluate against policy — same defense-in-depth as the MCP path.
        engine_result = await re_evaluate_against_policy(
            db, fetched=fetched, principal_id=principal,
        )
        if engine_result.verdict == "block":
            await db.commit()
            return {
                "status": "error",
                "reason": "policy_invalidated",
                "message": "Seller's policy changed since the quote was issued; ask them to re-run the quote.",
            }

        total_cents = int(fetched.offer_payload["pricing"]["total_cents"])
        if engine_result.verdict == "review" or not policy.auto_commit_enabled:
            queued = await queue_for_approval(
                db, fetched=fetched, tenant_id_uuid=policy.tenant_id, buyer_agent_id=principal,
            )
            await db.commit()
            return {
                "status": "pending_approval",
                "approval_id": queued.approval_id,
                "total_cents": total_cents,
                "expires_at": queued.expires_at.isoformat(),
                "message": (
                    "Deal goes to the seller's approval queue. Tell the buyer "
                    "you've submitted it and they'll hear back shortly."
                ),
            }

        try:
            committed = await commit_offer(
                db, fetched=fetched, tenant_id_uuid=policy.tenant_id,
                buyer_agent_id=principal, source="agent_gateway",
                buyer_reference=None,
            )
        except OfferRejectedError:
            return {"status": "error", "reason": "offer_rejected_by_seller"}
        await db.commit()

    return {
        "status": "accepted",
        "document_id": committed.document_id,
        "total_cents": committed.total_cents,
        "currency": committed.currency,
        "committed_at": committed.committed_at.isoformat(),
        "message": "Deal is committed. Confirm with the buyer and share the document ID.",
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def dispatch_tool(
    session: BuyerSession, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    try:
        if name == "fetch_catalog":
            return await handle_fetch_catalog(session)
        if name == "request_quote":
            return await handle_request_quote(
                session,
                line_items=arguments.get("line_items", []),
                client_name=arguments.get("client_name", "Guest"),
                deal_name=arguments.get("deal_name", ""),
                region=arguments.get("region", "US"),
            )
        if name == "accept_current_offer":
            return await handle_accept_current_offer(session)
        return {"status": "error", "reason": "unknown_tool", "name": name}
    except Exception as e:  # noqa: BLE001 — the tool result goes back to the model
        logger.exception("buyer_mediator tool %s failed", name)
        return {"status": "error", "reason": "tool_exception", "message": str(e)[:300]}
