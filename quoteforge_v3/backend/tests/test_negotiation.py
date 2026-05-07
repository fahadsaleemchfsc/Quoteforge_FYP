"""
Unit tests for the Negotiation package.

Two axes of coverage:

  1. Parser — verifies the forgiving-envelope / strict-schema split.
  2. Service retry loop — uses an in-memory FakeBackend so we can drive
     specific attempt sequences without touching any real model.

Run with:
  ./venv/bin/pytest tests/test_negotiation.py -v
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable

import pytest

from app.gateway.guardrails.engine import GuardrailEngine, PolicySnapshot
from app.gateway.negotiation.context import (
    NegotiationContext,
    NegotiationLine,
    PolicyHints,
    ProposedLine,
    ProposedOffer,
)
from app.gateway.negotiation.parser import (
    ModelOutputParseError,
    parse_proposed_offer,
)
from app.gateway.negotiation.service import NegotiationService


def _policy() -> PolicySnapshot:
    return PolicySnapshot(
        min_margin_percent=15.0,
        max_discount_percent=20.0,
        max_discount_with_approval_percent=35.0,
        allowed_regions=("US", "EU", "APAC"),
        currency_allowlist=("USD",),
        min_deal_size_cents=0,
        max_deal_size_cents=None,
        require_approval_above_cents=10_000_000_000,   # high — keep threshold out of these tests
    )


def _context(unit_price_ok: bool = True) -> NegotiationContext:
    return NegotiationContext(
        tenant_id="t-1",
        tenant_slug="default",
        buyer_region="US",
        buyer_client_name="TestCo",
        buyer_deal_name="Deal",
        lines=(
            NegotiationLine(
                sku="ABC",
                quantity=1,
                base_price_cents=10_000,
                min_price_floor_cents=6_000,
                product_name="Widget",
            ),
        ),
        policy_hints=PolicyHints(
            min_margin_percent=15.0,
            max_discount_percent=20.0,
            max_discount_with_approval_percent=35.0,
            allowed_regions=("US",),
            currency_allowlist=("USD",),
        ),
    )


# ───────────────────────── Parser ─────────────────────────

class TestParser:
    def test_happy_path(self) -> None:
        raw = json.dumps({
            "proposed_unit_prices": {"ABC": 9500},
            "rationale": "small discount",
            "confidence": 0.8,
        })
        offer = parse_proposed_offer(raw, _context())
        assert offer.lines[0].proposed_unit_price_cents == 9500
        assert offer.confidence == 0.8

    def test_strips_markdown_fences(self) -> None:
        raw = "```json\n{\"proposed_unit_prices\":{\"ABC\":9000},\"rationale\":\"\",\"confidence\":0.5}\n```"
        offer = parse_proposed_offer(raw, _context())
        assert offer.lines[0].proposed_unit_price_cents == 9000

    def test_finds_json_amid_prose(self) -> None:
        raw = 'Sure! Here is my proposal: {"proposed_unit_prices":{"ABC":9000},"rationale":"","confidence":0.5} hope this helps!'
        offer = parse_proposed_offer(raw, _context())
        assert offer.lines[0].proposed_unit_price_cents == 9000

    def test_rejects_sku_mismatch(self) -> None:
        raw = json.dumps({
            "proposed_unit_prices": {"OTHER": 9000},
            "rationale": "", "confidence": 0.5,
        })
        with pytest.raises(ModelOutputParseError):
            parse_proposed_offer(raw, _context())

    def test_rejects_no_json(self) -> None:
        with pytest.raises(ModelOutputParseError):
            parse_proposed_offer("completely not a response", _context())

    def test_clamps_confidence(self) -> None:
        raw = json.dumps({
            "proposed_unit_prices": {"ABC": 9000},
            "rationale": "", "confidence": 9.9,
        })
        offer = parse_proposed_offer(raw, _context())
        assert offer.confidence == 1.0


# ───────────────────────── Service retry loop ─────────────────────────

class FakeBackend:
    """Test harness — emits a scripted sequence of raw strings, one per call."""

    name = "fake"

    def __init__(self, scripted: list[str | Callable[[], str]]) -> None:
        self._scripted = scripted
        self.calls = 0

    async def generate(self, prompt: str) -> str:
        if self.calls >= len(self._scripted):
            raise RuntimeError("FakeBackend exhausted")
        item = self._scripted[self.calls]
        self.calls += 1
        return item() if callable(item) else item


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if hasattr(asyncio, 'get_event_loop') else asyncio.run(coro)


class TestRetryLoop:
    def _service(self, scripted: list) -> tuple[NegotiationService, FakeBackend]:
        backend = FakeBackend(scripted)
        service = NegotiationService(backend=backend, engine=GuardrailEngine())
        return service, backend

    def test_first_attempt_pass(self) -> None:
        # At unit_price = 10000, base = 10000 → discount 0% → passes.
        raw = json.dumps({
            "proposed_unit_prices": {"ABC": 10_000},
            "rationale": "at base",
            "confidence": 0.9,
        })
        service, backend = self._service([raw])

        result = asyncio.run(service.propose_and_validate(_context(), _policy(), "USD"))

        assert result.engine_result.verdict == "pass"
        assert len(result.attempts) == 1
        assert not result.fell_back
        assert backend.calls == 1

    def test_retries_then_passes(self) -> None:
        # Attempt 1: 4000 — below floor (6000) → block (min_margin)
        # Attempt 2: 10000 — base → pass
        too_low = json.dumps({"proposed_unit_prices": {"ABC": 4_000}, "rationale": "", "confidence": 0.5})
        at_base = json.dumps({"proposed_unit_prices": {"ABC": 10_000}, "rationale": "", "confidence": 0.9})
        service, backend = self._service([too_low, at_base])

        result = asyncio.run(service.propose_and_validate(_context(), _policy(), "USD"))

        assert result.engine_result.verdict == "pass"
        assert len(result.attempts) == 2
        assert result.attempts[0].verdict == "block"
        assert result.attempts[1].verdict == "pass"
        assert not result.fell_back

    def test_exhausts_retries_falls_back(self) -> None:
        always_low = json.dumps({"proposed_unit_prices": {"ABC": 1_000}, "rationale": "", "confidence": 0.4})
        # Script 3 attempts of too-low; then the 4th synthetic "attempt" is the
        # deterministic fallback which never hits the backend.
        service, backend = self._service([always_low, always_low, always_low])

        result = asyncio.run(service.propose_and_validate(_context(), _policy(), "USD"))

        assert result.fell_back is True
        # Last entry in attempts is the fallback record.
        assert result.attempts[-1].backend == "fallback"
        # Final verdict on base_price should be pass (margin is base*0.4 cushion).
        assert result.engine_result.verdict in ("pass", "review")
        assert backend.calls == 3

    def test_parse_error_counts_as_failed_attempt(self) -> None:
        garbage = "not json at all"
        at_base = json.dumps({"proposed_unit_prices": {"ABC": 10_000}, "rationale": "", "confidence": 0.9})
        service, backend = self._service([garbage, at_base])

        result = asyncio.run(service.propose_and_validate(_context(), _policy(), "USD"))

        assert result.attempts[0].verdict == "parse_error"
        assert result.attempts[1].verdict == "pass"
        assert not result.fell_back

    def test_timeout_counts_as_failed_attempt(self) -> None:
        """Backend sleeps past the configured timeout on first call."""
        # Patch timeout low for the test.
        from app.core.config import settings
        original = settings.NEGOTIATION_TIMEOUT_SECONDS
        settings.NEGOTIATION_TIMEOUT_SECONDS = 0.05

        async def slow_then_fast():
            await asyncio.sleep(0.2)
            return json.dumps({"proposed_unit_prices": {"ABC": 9_000}, "rationale": "", "confidence": 0.5})

        class SlowThenFastBackend:
            name = "fake"
            calls = 0

            async def generate(self, prompt: str) -> str:
                SlowThenFastBackend.calls += 1
                if SlowThenFastBackend.calls == 1:
                    await asyncio.sleep(0.2)
                return json.dumps({"proposed_unit_prices": {"ABC": 10_000}, "rationale": "", "confidence": 0.9})

        backend = SlowThenFastBackend()
        service = NegotiationService(backend=backend, engine=GuardrailEngine())
        try:
            result = asyncio.run(service.propose_and_validate(_context(), _policy(), "USD"))
            assert result.attempts[0].verdict == "timeout"
            assert result.engine_result.verdict == "pass"
        finally:
            settings.NEGOTIATION_TIMEOUT_SECONDS = original
