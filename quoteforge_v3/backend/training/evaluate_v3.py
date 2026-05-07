#!/usr/bin/env python3
"""
Evaluation harness for QuoteForge-V3 negotiation.

Runs 20 benchmark scenarios (defined below) through whichever backend is
selected via NEGOTIATION_MODEL_BACKEND and reports:

  - format_validity_pct    : % of outputs that parse to a valid ProposedOffer
  - margin_respect_pct     : % of outputs where every line is at or above floor
  - guardrail_pass_pct     : % where the engine returns "pass" or "review"
  - latency_ms             : p50 / p95

Compare V3 against V2 by running this script twice, once per backend:
  NEGOTIATION_MODEL_BACKEND=mlx  NEGOTIATION_MODEL_PATH=models/quoteforge-v2 ./venv/bin/python training/evaluate_v3.py
  NEGOTIATION_MODEL_BACKEND=mlx  NEGOTIATION_MODEL_PATH=models/quoteforge-v3 ./venv/bin/python training/evaluate_v3.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings                    # noqa: E402
from app.gateway.guardrails.engine import (             # noqa: E402
    GuardrailEngine,
    LineItemContext,
    OfferContext,
    PolicySnapshot,
)
from app.gateway.negotiation.context import (           # noqa: E402
    NegotiationContext,
    NegotiationLine,
    PolicyHints,
)
from app.gateway.negotiation.service import NegotiationService   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("evaluate_v3")


def _policy() -> PolicySnapshot:
    return PolicySnapshot(
        min_margin_percent=15.0,
        max_discount_percent=20.0,
        max_discount_with_approval_percent=35.0,
        allowed_regions=("US", "EU", "APAC", "UK", "PK"),
        currency_allowlist=("USD",),
        min_deal_size_cents=0,
        max_deal_size_cents=None,
        require_approval_above_cents=100_000_000,
    )


# 20 scenarios: varied sizes, regions, floor/base ratios.
BENCHMARK_SCENARIOS = [
    {
        "client": f"Benchmark-{i}",
        "region": ["US", "EU", "APAC", "UK"][i % 4],
        "lines": [
            {"sku": f"SKU-{i}-{j}",
             "qty": 1 + (i + j) % 5,
             "base_cents": 10_000 * (1 + i % 6),
             "floor_cents": int(10_000 * (1 + i % 6) * (0.6 + 0.05 * (j % 3)))}
            for j in range(1 + i % 3)
        ],
    }
    for i in range(20)
]


def _make_context(scenario: dict) -> NegotiationContext:
    policy = _policy()
    return NegotiationContext(
        tenant_id="bench",
        tenant_slug="bench",
        buyer_region=scenario["region"],
        buyer_client_name=scenario["client"],
        buyer_deal_name="benchmark",
        lines=tuple(
            NegotiationLine(
                sku=l["sku"],
                quantity=l["qty"],
                base_price_cents=l["base_cents"],
                min_price_floor_cents=l["floor_cents"],
                product_name=l["sku"],
            )
            for l in scenario["lines"]
        ),
        policy_hints=PolicyHints(
            min_margin_percent=policy.min_margin_percent,
            max_discount_percent=policy.max_discount_percent,
            max_discount_with_approval_percent=policy.max_discount_with_approval_percent,
            allowed_regions=policy.allowed_regions,
            currency_allowlist=policy.currency_allowlist,
        ),
    )


async def main() -> None:
    service = NegotiationService()
    policy = _policy()

    format_valid = 0
    margin_ok = 0
    guardrail_pass = 0
    latencies: list[int] = []

    for idx, scenario in enumerate(BENCHMARK_SCENARIOS):
        ctx = _make_context(scenario)
        validated = await service.propose_and_validate(ctx, policy, currency="USD")

        # Format validity: did the FIRST attempt parse? (retries mask the metric.)
        first = validated.attempts[0]
        if first.proposed is not None:
            format_valid += 1
            if all(
                l.proposed_unit_price_cents >= ctx.lines[i].min_price_floor_cents
                for i, l in enumerate(first.proposed.lines)
            ):
                margin_ok += 1

        if validated.engine_result.verdict in ("pass", "review"):
            guardrail_pass += 1
        latencies.extend(a.latency_ms for a in validated.attempts if a.latency_ms > 0)

    n = len(BENCHMARK_SCENARIOS)
    report = {
        "backend": settings.NEGOTIATION_MODEL_BACKEND,
        "model_path": settings.NEGOTIATION_MODEL_PATH,
        "n_scenarios": n,
        "format_validity_pct": 100 * format_valid / n,
        "margin_respect_pct": 100 * margin_ok / n,
        "guardrail_pass_pct": 100 * guardrail_pass / n,
        "latency_p50_ms": int(statistics.median(latencies)) if latencies else 0,
        "latency_p95_ms": int(sorted(latencies)[int(0.95 * len(latencies)) - 1]) if latencies else 0,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
