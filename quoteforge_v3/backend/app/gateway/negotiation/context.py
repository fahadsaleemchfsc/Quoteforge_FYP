"""
Dataclasses for the negotiation loop.

Three layers, deliberately separated:

  NegotiationContext  ← what we give the model
  ProposedOffer       ← what the model gives back (raw, pre-guardrail)
  EngineResult        ← what the guardrail engine says about the proposal

The model never sees a guardrail-validated offer. The buyer never sees a
model-proposed offer that hasn't been through guardrails. That separation
is the architecture's thesis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NegotiationLine:
    sku: str
    quantity: int
    base_price_cents: int
    min_price_floor_cents: int     # internal, fed to model so it stays above floor
    product_name: str
    description: str = ""


@dataclass(frozen=True)
class SimilarDeal:
    """RAG result — a closed-won deal that resembles this request."""
    summary: str
    final_total_cents: int
    final_discount_percent: float


@dataclass(frozen=True)
class PolicyHints:
    """The subset of GuardrailPolicy we tell the model, so it knows the rules
    it's being judged against. Given to the model in the prompt; the authoritative
    enforcement is still the Guardrail Engine on the output."""
    min_margin_percent: float
    max_discount_percent: float
    max_discount_with_approval_percent: float
    allowed_regions: tuple[str, ...]
    currency_allowlist: tuple[str, ...]


@dataclass(frozen=True)
class NegotiationContext:
    tenant_id: str                      # UUID
    tenant_slug: str
    buyer_region: str
    buyer_client_name: str
    buyer_deal_name: str
    buyer_metadata: dict[str, Any] = field(default_factory=dict)
    lines: tuple[NegotiationLine, ...] = ()
    similar_deals: tuple[SimilarDeal, ...] = ()
    policy_hints: PolicyHints | None = None


@dataclass(frozen=True)
class ProposedLine:
    sku: str
    quantity: int
    proposed_unit_price_cents: int


@dataclass(frozen=True)
class ProposedOffer:
    lines: tuple[ProposedLine, ...]
    rationale: str                      # internal — never shown to buyer
    confidence: float                   # 0.0–1.0, from the model
    raw_model_output: str               # verbatim, for replay


@dataclass(frozen=True)
class NegotiationAttempt:
    """One iteration of the retry loop — logged to Replay Layer."""
    attempt_number: int                 # 1-indexed
    backend: str                        # "mlx" | "ollama" | "vllm" | "stub" | "fallback"
    proposed: ProposedOffer | None
    verdict: str                        # "pass" | "review" | "block" | "timeout" | "parse_error"
    blocking_check_names: tuple[str, ...] = ()
    latency_ms: int = 0
    error: str | None = None
