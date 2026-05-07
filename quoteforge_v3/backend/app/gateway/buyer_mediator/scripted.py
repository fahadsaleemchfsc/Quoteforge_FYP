"""
Scripted mediator — deterministic fallback for when ANTHROPIC_API_KEY is unset.

Mirrors the BuyerMediatorService contract (same turn output shape) but uses
regex-keyed intent matching instead of an LLM. Good enough to demo the full
buyer-room round-trip (catalog → quote → accept) with no external dependency.

Intents detected (case-insensitive):
  - "catalog" / "what do you have" / "products" → fetch_catalog
  - "I need <N> <sku-like-text>" / "quote for <N> X" → request_quote
  - "accept" / "yes" / "go ahead" / "commit" → accept_current_offer
  - otherwise → ask a clarifying question

This lives behind the same service surface so wiring is unchanged.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.gateway.buyer_mediator.session import BuyerSession
from app.gateway.buyer_mediator.tools import dispatch_tool

logger = logging.getLogger(__name__)

# Relaxed "n sku" pattern: "20 enterprise licenses" / "5 ENT-LIC" / "3 seats"
_QUANTITY_PATTERN = re.compile(
    r"(?P<qty>\d+)\s*(?:x|×)?\s*(?P<sku>[A-Za-z][A-Za-z0-9 \-]{2,40})",
    flags=re.IGNORECASE,
)

_ACCEPT_MARKERS = re.compile(
    r"\b(accept|accept it|yes\b|go ahead|commit|ship it|let'?s do it|do it|proceed)\b",
    flags=re.IGNORECASE,
)
_CATALOG_MARKERS = re.compile(
    r"\b(catalog|what do you have|what do you sell|products|offerings|skus?)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ScriptedTurn:
    assistant_text: str
    tool_calls: list[dict[str, Any]]
    offer_state: dict[str, Any] | None


def _offer_snapshot(session: BuyerSession) -> dict[str, Any] | None:
    if session.offer is None:
        return None
    p = session.offer.payload
    return {
        "offer_id": p.get("offer_id"),
        "valid_until": p.get("valid_until"),
        "client_name": p.get("client_name"),
        "line_items": p.get("line_items", []),
        "pricing": p.get("pricing", {}),
        "requires_approval": session.offer.requires_approval,
    }


def _format_money(amount: Any, currency: str = "USD") -> str:
    try:
        return f"${float(amount):,.2f}"
    except (TypeError, ValueError):
        return str(amount)


async def _catalog_reply(session: BuyerSession, catalog_cache: list[dict] | None) -> ScriptedTurn:
    if catalog_cache is None:
        result = await dispatch_tool(session, "fetch_catalog", {})
        catalog_cache = result.get("products", [])
    names = [p.get("name", p.get("sku")) for p in catalog_cache[:5]]
    if not names:
        return ScriptedTurn(
            assistant_text=(
                "I don't have anything in this catalog right now — the seller may still be "
                "setting up products. Try again later."
            ),
            tool_calls=[{"name": "fetch_catalog", "input": {}, "result_summary": "catalog count=0"}],
            offer_state=None,
        )
    bullet = "\n".join(f"  • {p.get('name')} ({p.get('sku')}) — {_format_money(p.get('base_price'))}"
                       for p in catalog_cache[:5])
    return ScriptedTurn(
        assistant_text=(
            f"Here's what I can quote you:\n{bullet}\n\n"
            f"Tell me what you need — how many of which, and what region you're in — "
            f"and I'll put together a quote."
        ),
        tool_calls=[{"name": "fetch_catalog", "input": {}, "result_summary": f"catalog count={len(catalog_cache)}"}],
        offer_state=_offer_snapshot(session),
    )


def _best_sku_match(text: str, catalog: list[dict]) -> str | None:
    """Find a catalog SKU the buyer mentioned by name or exact SKU."""
    low = text.lower()
    # Exact SKU first
    for p in catalog:
        if p.get("sku", "").lower() in low:
            return p["sku"]
    # Name match
    for p in catalog:
        name = (p.get("name") or "").lower()
        # Require at least two matching words to avoid noise.
        words = [w for w in re.split(r"\W+", name) if len(w) > 3]
        if words and sum(1 for w in words if w in low) >= min(2, len(words)):
            return p["sku"]
    return None


async def _try_quote(session: BuyerSession, user_message: str) -> ScriptedTurn | None:
    # Fetch catalog once; cache on session.
    cache_key = "_scripted_catalog"
    catalog = getattr(session, cache_key, None)
    if catalog is None:
        result = await dispatch_tool(session, "fetch_catalog", {})
        catalog = result.get("products", [])
        setattr(session, cache_key, catalog)

    matches = []
    for m in _QUANTITY_PATTERN.finditer(user_message):
        qty = int(m.group("qty"))
        sku_text = m.group("sku").strip()
        sku = _best_sku_match(sku_text, catalog)
        if sku and qty > 0:
            matches.append({"sku": sku, "quantity": qty})

    if not matches:
        return None

    # Extract region if mentioned.
    region = "US"
    for r in ("US", "EU", "APAC", "UK"):
        if re.search(rf"\b{r}\b", user_message, flags=re.IGNORECASE):
            region = r
            break

    result = await dispatch_tool(session, "request_quote", {
        "line_items": matches,
        "client_name": "Guest",
        "deal_name": "Buyer-room quote",
        "region": region,
    })
    call_log = [{"name": "request_quote", "input": {"line_items": matches, "region": region},
                 "result_summary": result.get("status", "?")}]

    if result.get("status") == "issued":
        offer = result["offer"]
        pricing = offer["pricing"]
        line_bits = "\n".join(
            f"  • {li['sku']} × {li['quantity']} @ {_format_money(li['unit_price'])} = {_format_money(li['line_total'])}"
            for li in offer["line_items"]
        )
        approval = (
            "\n\nThis amount needs seller approval before it commits — when you say yes, I'll queue it."
            if offer["requires_approval"] else
            "\n\nSay the word and I'll commit it."
        )
        text = (
            f"Here's the quote:\n{line_bits}\n\n"
            f"Subtotal: {_format_money(pricing.get('subtotal'))}\n"
            f"Discount: -{_format_money(pricing.get('discount', 0))}\n"
            f"Total: {_format_money(pricing.get('total'))} {pricing.get('currency', 'USD')}"
            f"{approval}"
        )
    elif result.get("status") == "rejected":
        reason = result.get("reason", "blocked")
        adjustment = result.get("suggested_adjustment") or {}
        hint = ""
        lines = adjustment.get("line_items") if isinstance(adjustment, dict) else None
        if lines:
            hint = (
                "\n\nThe seller can accept if the unit prices are at least:\n"
                + "\n".join(f"  • {l['sku']}: {_format_money(l['min_acceptable_unit_price_cents'] / 100)}"
                            for l in lines)
            )
        text = (
            f"The seller's pricing rules won't let this quote through ({reason}).{hint}\n\n"
            f"Want me to try different quantities or SKUs?"
        )
    else:
        text = (
            "Something went sideways on that quote request. "
            "Try rephrasing with a quantity and SKU — like '5 ENT-LIC' or '20 enterprise licenses'."
        )

    return ScriptedTurn(
        assistant_text=text, tool_calls=call_log, offer_state=_offer_snapshot(session),
    )


async def _try_accept(session: BuyerSession) -> ScriptedTurn:
    result = await dispatch_tool(session, "accept_current_offer", {})
    call_log = [{"name": "accept_current_offer", "input": {}, "result_summary": result.get("status", "?")}]
    status = result.get("status")
    if status == "accepted":
        text = (
            f"Done — deal committed. Document ID {result.get('document_id')}, "
            f"{_format_money(result.get('total_cents', 0) / 100)} {result.get('currency', 'USD')}."
        )
    elif status == "pending_approval":
        text = (
            f"Submitted to the seller's approval queue. Approval ID "
            f"{result.get('approval_id', '')[:8]}… — they'll review and get back to you shortly."
        )
    else:
        reason = result.get("reason", "unknown")
        text = f"Couldn't commit right now: {reason}. Ask me for a fresh quote and we'll try again."
    return ScriptedTurn(
        assistant_text=text, tool_calls=call_log, offer_state=_offer_snapshot(session),
    )


async def scripted_turn(session: BuyerSession, user_message: str) -> ScriptedTurn:
    msg = user_message.strip()
    if _ACCEPT_MARKERS.search(msg) and session.offer is not None:
        return await _try_accept(session)
    if _CATALOG_MARKERS.search(msg):
        return await _catalog_reply(session, getattr(session, "_scripted_catalog", None))

    # Try to infer a quote request.
    quote = await _try_quote(session, msg)
    if quote is not None:
        return quote

    return ScriptedTurn(
        assistant_text=(
            "Tell me what you need and I'll put together a quote — e.g. "
            "'5 enterprise licenses' or 'I want 20 seats in EU'. "
            "You can also ask me what's in the catalog."
        ),
        tool_calls=[],
        offer_state=_offer_snapshot(session),
    )
