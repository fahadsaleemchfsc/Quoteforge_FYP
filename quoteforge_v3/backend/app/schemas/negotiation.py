"""Pydantic schemas for the admin negotiations dashboard."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AttemptOut(BaseModel):
    attempt_number: int
    backend: str
    verdict: str
    blocking_check_names: list[str]
    latency_ms: int
    proposed_lines: list[dict[str, Any]] | None = None
    rationale: str | None = None
    confidence: float | None = None
    error: str | None = None
    fell_back: bool = False
    created_at: datetime


OutcomeLiteral = Literal[
    "first_try",      # single attempt, verdict pass/review
    "retried",        # multiple attempts, eventually pass/review
    "fell_back",      # retry budget exhausted, used deterministic
    "timed_out",      # at least one timeout in the chain
]


class NegotiationRow(BaseModel):
    offer_id: str
    first_attempt_at: datetime
    last_attempt_at: datetime
    attempt_count: int
    final_verdict: str
    outcome: OutcomeLiteral
    backend: str                         # backend used in the FIRST attempt
    best_confidence: float | None = None
    total_latency_ms: int = 0
    attempts: list[AttemptOut] = Field(default_factory=list)


class NegotiationsList(BaseModel):
    rows: list[NegotiationRow]
    total: int
    page: int
    per_page: int
