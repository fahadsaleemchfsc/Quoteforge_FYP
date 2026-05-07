"""
NegotiationService — the retry loop.

Contract:
  propose_and_validate(context, policy_snapshot) → ValidatedProposal
    ValidatedProposal carries:
      - final_lines: list[ProposedLine]         (authoritative prices)
      - engine_result: EngineResult             (the pass/review verdict)
      - attempts: tuple[NegotiationAttempt, ...] (the full chain)
      - fell_back: bool

The service never returns a blocked proposal — if the AI can't satisfy
guardrails within NEGOTIATION_MAX_RETRIES, it calls deterministic_fallback
(prices = base_price from the catalog) and re-evaluates. A deterministic
proposal at base_price always passes margin+discount checks (discount=0,
margin=base cushion over floor), so the loop always terminates with either
a pass or review verdict — never a block.

Timeouts on the model call count as failed attempts against the retry budget.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.core.config import settings
from app.gateway.guardrails.engine import (
    EngineResult,
    GuardrailEngine,
    LineItemContext,
    OfferContext,
    PolicySnapshot,
)
from app.gateway.negotiation.context import (
    NegotiationAttempt,
    NegotiationContext,
    ProposedLine,
    ProposedOffer,
)
from app.gateway.negotiation.model import ModelBackend, get_backend
from app.gateway.negotiation.parser import (
    ModelOutputParseError,
    parse_proposed_offer,
)
from app.gateway.negotiation.prompt import build_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidatedProposal:
    final_lines: tuple[ProposedLine, ...]
    engine_result: EngineResult
    attempts: tuple[NegotiationAttempt, ...]
    fell_back: bool
    backend_name: str
    total_cents: int


def _offer_context_from_proposal(
    proposal: tuple[ProposedLine, ...],
    context: NegotiationContext,
    currency: str,
) -> tuple[OfferContext, int]:
    """Assemble the guardrail input from a proposal. Returns (context, total_cents)."""
    by_sku = {l.sku: l for l in context.lines}
    items: list[LineItemContext] = []
    total = 0
    for p in proposal:
        source = by_sku[p.sku]
        items.append(LineItemContext(
            sku=p.sku,
            quantity=p.quantity,
            unit_price_cents=p.proposed_unit_price_cents,
            base_price_cents=source.base_price_cents,
            min_price_floor_cents=source.min_price_floor_cents,
        ))
        total += p.proposed_unit_price_cents * p.quantity
    offer_ctx = OfferContext(
        tenant_id=context.tenant_id,
        line_items=tuple(items),
        total_cents=total,
        currency=currency,
        buyer_region=context.buyer_region,
    )
    return offer_ctx, total


def _deterministic_fallback(context: NegotiationContext) -> tuple[ProposedLine, ...]:
    """Catalog base_price per line. Always passes margin/discount checks."""
    return tuple(
        ProposedLine(
            sku=l.sku,
            quantity=l.quantity,
            proposed_unit_price_cents=l.base_price_cents,
        )
        for l in context.lines
    )


class NegotiationService:
    def __init__(
        self,
        backend: ModelBackend | None = None,
        engine: GuardrailEngine | None = None,
    ) -> None:
        self._backend = backend or get_backend()
        self._engine = engine or GuardrailEngine()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    async def propose_and_validate(
        self,
        context: NegotiationContext,
        policy: PolicySnapshot,
        currency: str,
    ) -> ValidatedProposal:
        attempts: list[NegotiationAttempt] = []

        feedback: tuple = ()
        for attempt_number in range(1, settings.NEGOTIATION_MAX_RETRIES + 1):
            attempt = await self._single_attempt(
                context=context,
                policy=policy,
                currency=currency,
                attempt_number=attempt_number,
                retry_feedback=feedback,
            )
            attempts.append(attempt)

            if attempt.verdict in ("pass", "review"):
                assert attempt.proposed is not None      # noqa: S101 — contract guarantee
                offer_ctx, total_cents = _offer_context_from_proposal(
                    attempt.proposed.lines, context, currency,
                )
                engine_result = self._engine.evaluate(offer_ctx, policy)
                return ValidatedProposal(
                    final_lines=attempt.proposed.lines,
                    engine_result=engine_result,
                    attempts=tuple(attempts),
                    fell_back=False,
                    backend_name=self._backend.name,
                    total_cents=total_cents,
                )

            # Block / timeout / parse_error — feed the blocking checks back in.
            if attempt.proposed is not None:
                # Re-evaluate to pull CheckResults to use as feedback.
                offer_ctx, _ = _offer_context_from_proposal(
                    attempt.proposed.lines, context, currency,
                )
                engine_result = self._engine.evaluate(offer_ctx, policy)
                feedback = tuple(cr for cr in engine_result.check_results if cr.verdict != "pass")

        # Retries exhausted — deterministic fallback.
        fallback_lines = _deterministic_fallback(context)
        offer_ctx, total_cents = _offer_context_from_proposal(fallback_lines, context, currency)
        engine_result = self._engine.evaluate(offer_ctx, policy)
        attempts.append(NegotiationAttempt(
            attempt_number=len(attempts) + 1,
            backend="fallback",
            proposed=ProposedOffer(
                lines=fallback_lines,
                rationale="deterministic fallback after retry budget exhausted",
                confidence=1.0,
                raw_model_output="",
            ),
            verdict=engine_result.verdict,
            blocking_check_names=tuple(
                cr.name for cr in engine_result.check_results if cr.verdict == "block"
            ),
            latency_ms=0,
        ))
        return ValidatedProposal(
            final_lines=fallback_lines,
            engine_result=engine_result,
            attempts=tuple(attempts),
            fell_back=True,
            backend_name=self._backend.name,
            total_cents=total_cents,
        )

    async def _single_attempt(
        self,
        *,
        context: NegotiationContext,
        policy: PolicySnapshot,
        currency: str,
        attempt_number: int,
        retry_feedback: tuple,
    ) -> NegotiationAttempt:
        prompt = build_prompt(context, retry_feedback=retry_feedback)
        start = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                self._backend.generate(prompt),
                timeout=settings.NEGOTIATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("negotiation attempt %d timed out after %dms", attempt_number, elapsed)
            return NegotiationAttempt(
                attempt_number=attempt_number,
                backend=self._backend.name,
                proposed=None,
                verdict="timeout",
                latency_ms=elapsed,
                error="timeout",
            )
        except Exception as e:     # noqa: BLE001 — backend may surface any error; treat as failed attempt
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning("negotiation attempt %d backend error: %s", attempt_number, e)
            return NegotiationAttempt(
                attempt_number=attempt_number,
                backend=self._backend.name,
                proposed=None,
                verdict="backend_error",
                latency_ms=elapsed,
                error=str(e)[:200],
            )

        elapsed = int((time.monotonic() - start) * 1000)
        try:
            proposed = parse_proposed_offer(raw, context)
        except ModelOutputParseError as e:
            logger.warning("negotiation attempt %d parse error: %s", attempt_number, e)
            return NegotiationAttempt(
                attempt_number=attempt_number,
                backend=self._backend.name,
                proposed=None,
                verdict="parse_error",
                latency_ms=elapsed,
                error=str(e)[:200],
            )

        # Evaluate proposal through the engine.
        offer_ctx, _ = _offer_context_from_proposal(proposed.lines, context, currency)
        engine_result = self._engine.evaluate(offer_ctx, policy)
        blocking = tuple(cr.name for cr in engine_result.check_results if cr.verdict == "block")

        return NegotiationAttempt(
            attempt_number=attempt_number,
            backend=self._backend.name,
            proposed=proposed,
            verdict=engine_result.verdict,
            blocking_check_names=blocking,
            latency_ms=elapsed,
        )
