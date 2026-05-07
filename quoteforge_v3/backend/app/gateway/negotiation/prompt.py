"""
Prompt construction for the Negotiation AI.

Keep the prompt surface small and stable. The model is trained against this
exact layout — every refactor here invalidates the training data. If you need
to add fields, add them in a backward-compatible way and document below.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from app.gateway.guardrails.engine import CheckResult
from app.gateway.negotiation.context import NegotiationContext

# Constant template used at both train and inference time. Keep any edits here
# mirrored in training/prepare_negotiation_dataset.py.
SYSTEM_INSTRUCTION = (
    "You are QuoteForge's negotiation agent for a B2B seller. "
    "Given the buyer's request, the seller's price floors, and similar past "
    "deals, propose concrete unit prices. Output a SINGLE JSON object with "
    "keys: proposed_unit_prices (object of sku→cents), rationale (string "
    "under 200 chars, internal only), confidence (0.0–1.0). Do not emit any "
    "text outside the JSON. Do not propose a unit price below the line's "
    "min_price_floor_cents; doing so will be rejected by deterministic guardrails."
)


def _line_for_prompt(line) -> dict[str, Any]:
    return {
        "sku": line.sku,
        "product_name": line.product_name,
        "quantity": line.quantity,
        "base_price_cents": line.base_price_cents,
        "min_price_floor_cents": line.min_price_floor_cents,
    }


def _policy_for_prompt(policy) -> dict[str, Any]:
    if policy is None:
        return {}
    return {
        "min_margin_percent": policy.min_margin_percent,
        "max_discount_percent": policy.max_discount_percent,
        "max_discount_with_approval_percent": policy.max_discount_with_approval_percent,
        "allowed_regions": list(policy.allowed_regions),
        "currency_allowlist": list(policy.currency_allowlist),
    }


def _retry_feedback_block(retry_feedback: tuple[CheckResult, ...] | None) -> dict[str, Any] | None:
    if not retry_feedback:
        return None
    # Only include checks that actually blocked or flagged. No internal prose
    # from the engine — just the name and suggested adjustment the engine
    # surfaced (these are already safe to echo back because they describe the
    # rule, not the buyer).
    return [
        {
            "rule": cr.name,
            "verdict": cr.verdict,
            "suggested_adjustment": cr.suggested_adjustment,
        }
        for cr in retry_feedback
        if cr.verdict != "pass"
    ]


def build_prompt(
    context: NegotiationContext,
    retry_feedback: tuple[CheckResult, ...] | None = None,
) -> str:
    """Serialize the NegotiationContext into the exact prompt layout the model
    was fine-tuned against. JSON-in-JSON-out, no free-text prose."""
    request_block: dict[str, Any] = {
        "buyer": {
            "region": context.buyer_region,
            "client_name": context.buyer_client_name,
            "deal_name": context.buyer_deal_name,
        },
        "line_items": [_line_for_prompt(l) for l in context.lines],
        "policy": _policy_for_prompt(context.policy_hints),
    }
    if context.similar_deals:
        request_block["similar_deals"] = [asdict(d) for d in context.similar_deals]
    feedback = _retry_feedback_block(retry_feedback)
    if feedback:
        request_block["previous_attempt_feedback"] = feedback

    return (
        f"<|system|>\n{SYSTEM_INSTRUCTION}\n"
        f"<|user|>\n{json.dumps(request_block, separators=(',', ':'))}\n"
        f"<|assistant|>\n"
    )
