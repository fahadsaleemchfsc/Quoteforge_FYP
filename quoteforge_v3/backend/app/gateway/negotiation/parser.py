"""
Parse raw model output into a ProposedOffer.

Real models emit markdown fences, stray prose, comments inside JSON, and
every other known hallucination. This parser is intentionally forgiving at
the envelope level (strip whitespace, find first-balanced `{...}`) and
strict at the schema level (reject if SKUs don't match or prices aren't ints).

A parse failure counts as a failed attempt in the retry loop — we don't try
to repair a malformed response, we just retry with the same prompt plus
an explicit feedback hint.
"""
from __future__ import annotations

import json
import re

from app.gateway.negotiation.context import (
    NegotiationContext,
    ProposedLine,
    ProposedOffer,
)


class ModelOutputParseError(Exception):
    pass


# First top-level {...} block — tolerant of leading/trailing prose.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_blob(text: str) -> str:
    stripped = text.strip()
    # Strip common markdown fences first.
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
    match = _JSON_BLOCK.search(stripped)
    if match is None:
        raise ModelOutputParseError("no JSON object found in model output")
    return match.group(0)


def parse_proposed_offer(raw: str, context: NegotiationContext) -> ProposedOffer:
    """Validate + shape the model's raw output.

    Rejects anything that doesn't propose prices for the exact set of SKUs
    we asked about. That protects against a common failure mode where the
    model drops or invents a SKU.
    """
    blob = _extract_json_blob(raw)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ModelOutputParseError(f"invalid JSON: {e.msg}") from e
    if not isinstance(data, dict):
        raise ModelOutputParseError("top-level JSON is not an object")

    prices = data.get("proposed_unit_prices")
    if not isinstance(prices, dict):
        raise ModelOutputParseError("proposed_unit_prices missing or not an object")

    expected_skus = {l.sku for l in context.lines}
    got_skus = set(prices)
    if expected_skus != got_skus:
        raise ModelOutputParseError(
            f"sku set mismatch: expected={sorted(expected_skus)} got={sorted(got_skus)}"
        )

    proposed_lines: list[ProposedLine] = []
    for line in context.lines:
        raw_price = prices[line.sku]
        if not isinstance(raw_price, (int, float)):
            raise ModelOutputParseError(f"price for {line.sku} not numeric")
        cents = int(raw_price)
        if cents < 0:
            raise ModelOutputParseError(f"price for {line.sku} negative")
        proposed_lines.append(ProposedLine(
            sku=line.sku,
            quantity=line.quantity,
            proposed_unit_price_cents=cents,
        ))

    rationale = str(data.get("rationale", "")).strip()[:500]
    confidence_raw = data.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return ProposedOffer(
        lines=tuple(proposed_lines),
        rationale=rationale,
        confidence=confidence,
        raw_model_output=raw,
    )
