"""
BuyerMediatorService — Claude Sonnet orchestrator for buyer-facing chats.

Turn shape:
  1. Append the buyer's message to session.messages.
  2. Call Claude with (system prompt + tools + full history).
  3. While the response has tool_use blocks: execute each, append tool_result,
     call Claude again. Loop until Claude emits a plain text response.
  4. Return the final text + a snapshot of session.offer.

System prompt + tool schema are marked cache-eligible so each follow-up turn
only re-serializes the new messages.

The service does NOT return the signature, offer's payload internals, or
anything the buyer shouldn't see. It returns a small `offer_state` dict with
the fields the UI should render.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from app.core.config import settings
from app.gateway.buyer_mediator.scripted import scripted_turn
from app.gateway.buyer_mediator.session import BuyerSession
from app.gateway.buyer_mediator.tools import TOOL_SCHEMA, dispatch_tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are QuoteForge's buyer-room negotiation assistant, helping a human "
    "buyer get a quote from {seller_name}. You have tool access to their "
    "product catalog, can request priced quotes from them, and can commit a "
    "deal once the buyer explicitly agrees.\n\n"
    "How to work:\n"
    "- On the first turn of a conversation, call fetch_catalog so you know "
    "what SKUs exist. Don't dump the whole catalog at the buyer unless they "
    "ask — lead with questions about what they need.\n"
    "- When you have enough info (SKUs, quantities, region), call request_quote. "
    "Present the returned pricing to the buyer in plain language — unit price, "
    "quantity, line totals, total. Mention if it requires seller approval.\n"
    "- If request_quote is rejected, explain in plain language what the seller "
    "can and can't do. If suggested_adjustment says prices need to be higher, "
    "describe the floor as 'the seller can't go below X' without revealing "
    "internal policy numbers.\n"
    "- Only call accept_current_offer when the buyer has explicitly said yes "
    "to the specific numbers you quoted. Confirm back once committed.\n\n"
    "What you never reveal:\n"
    "- Signatures, offer IDs, internal policy values like 'min_margin_percent', "
    "  minimum price floors, or any field marked internal.\n"
    "- The exact language 'guardrail', 'min_margin', 'compliance' — translate "
    "  to natural buyer-facing language ('seller's pricing rules', 'their floor').\n\n"
    "Tone: friendly, direct, business-like. Short paragraphs. No emoji."
)


@dataclass(frozen=True)
class MediatorTurn:
    assistant_text: str
    tool_calls: list[dict[str, Any]]     # names of tools called, for logs / replay
    offer_state: dict[str, Any] | None   # buyer-visible shape, or None


def _client() -> anthropic.AsyncAnthropic:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _offer_snapshot(session: BuyerSession) -> dict[str, Any] | None:
    """Buyer-visible subset of the stored offer. Never includes signature."""
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


def _extract_tool_uses(response: anthropic.types.Message) -> list[anthropic.types.ToolUseBlock]:
    return [b for b in response.content if b.type == "tool_use"]


def _extract_text(response: anthropic.types.Message) -> str:
    parts = [b.text for b in response.content if b.type == "text"]
    return "".join(parts).strip()


class BuyerMediatorService:
    """One instance per app process — the Anthropic client is reusable."""

    def __init__(self) -> None:
        # Lazy — don't instantiate the client until a real call happens.
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = _client()
        return self._client

    async def greet(self, session: BuyerSession, seller_name: str, product_names: list[str]) -> MediatorTurn:
        """The auto-seed opening message. Canned — no LLM call needed."""
        sample = ", ".join(product_names[:3]) if product_names else "a range of products"
        text = (
            f"Hi! I'm helping you put together a quote with {seller_name}. "
            f"They offer {sample}. Tell me what you need — how many of what, "
            f"your budget, and any specific requirements — and I'll work it "
            f"out with them."
        )
        session.messages.append({"role": "assistant", "content": text})
        return MediatorTurn(assistant_text=text, tool_calls=[], offer_state=None)

    async def turn(
        self,
        session: BuyerSession,
        seller_name: str,
        user_message: str,
    ) -> MediatorTurn:
        """Run one conversational turn. May involve multiple tool-use rounds."""
        # Deterministic fallback — runs when no Anthropic credentials are
        # configured. Calls the same internal tools; produces a simpler text
        # reply. Keeps the buyer-room demo functional in credential-free envs.
        if not settings.ANTHROPIC_API_KEY:
            logger.info("buyer_mediator: no ANTHROPIC_API_KEY, using scripted fallback")
            scripted = await scripted_turn(session, user_message)
            session.messages.append({"role": "user", "content": user_message})
            session.messages.append({"role": "assistant", "content": scripted.assistant_text})
            return MediatorTurn(
                assistant_text=scripted.assistant_text,
                tool_calls=scripted.tool_calls,
                offer_state=scripted.offer_state,
            )

        session.messages.append({"role": "user", "content": user_message})

        system_text = SYSTEM_PROMPT.format(seller_name=seller_name)
        # Cache the system prompt + tool schema block — each turn only pays
        # for the new message tokens.
        system_blocks = [{
            "type": "text", "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }]
        tools_with_cache = [
            {**t, "cache_control": {"type": "ephemeral"}} if i == len(TOOL_SCHEMA) - 1 else t
            for i, t in enumerate(TOOL_SCHEMA)
        ]

        client = self._get_client()
        tool_names_called: list[dict[str, Any]] = []
        max_rounds = 6      # safety — bail if Claude loops on tool calls

        for _ in range(max_rounds):
            response = await client.messages.create(
                model=settings.BUYER_ROOM_MODEL,
                max_tokens=settings.BUYER_ROOM_MAX_TOKENS,
                system=system_blocks,
                tools=tools_with_cache,
                messages=session.messages,
            )

            if response.stop_reason != "tool_use":
                text = _extract_text(response) or "(no response)"
                # Append the assistant's text so history is coherent.
                session.messages.append({"role": "assistant", "content": response.content})
                return MediatorTurn(
                    assistant_text=text,
                    tool_calls=tool_names_called,
                    offer_state=_offer_snapshot(session),
                )

            # Tool-use round — append the assistant's full content (tool_use blocks
            # must be preserved in history) then dispatch each tool and append results.
            session.messages.append({"role": "assistant", "content": response.content})
            tool_uses = _extract_tool_uses(response)

            tool_result_blocks: list[dict[str, Any]] = []
            for tu in tool_uses:
                args = tu.input if isinstance(tu.input, dict) else {}
                result = await dispatch_tool(session, tu.name, args)
                tool_names_called.append({"name": tu.name, "input": args, "result_summary": _summarize(result)})
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, default=str),
                })

            session.messages.append({"role": "user", "content": tool_result_blocks})

        # Ran out of tool rounds — still return the last text if any.
        logger.warning("buyer_mediator: hit max_rounds without final text session=%s", session.session_id)
        return MediatorTurn(
            assistant_text="(I'm looping on tool calls — can you clarify what you need?)",
            tool_calls=tool_names_called,
            offer_state=_offer_snapshot(session),
        )


def _summarize(result: dict[str, Any]) -> str:
    """Short tag of what a tool returned — for logs + replay events."""
    status = result.get("status")
    if status == "issued":
        offer = result.get("offer", {})
        pricing = offer.get("pricing", {})
        return f"issued total={pricing.get('total')} {pricing.get('currency', '')}"
    if status == "accepted":
        return f"accepted doc={result.get('document_id')}"
    if status == "pending_approval":
        return f"pending_approval approval={result.get('approval_id')}"
    if status == "rejected":
        return f"rejected reason={result.get('reason')}"
    if status == "error":
        return f"error reason={result.get('reason')}"
    if "products" in result:
        return f"catalog count={result.get('count', 0)}"
    return status or "ok"
