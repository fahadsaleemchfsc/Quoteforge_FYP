"""Negotiation AI — fine-tuned Llama-3.2-1B V3 wrapped by guardrails."""
from app.gateway.negotiation.context import (
    NegotiationContext,
    NegotiationLine,
    ProposedOffer,
    ProposedLine,
)
from app.gateway.negotiation.service import NegotiationService

__all__ = [
    "NegotiationContext",
    "NegotiationLine",
    "ProposedOffer",
    "ProposedLine",
    "NegotiationService",
]
