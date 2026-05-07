"""Pydantic schemas for the tenant config admin endpoint."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


NegotiationModeLiteral = Literal["ai_first", "deterministic"]


class TenantConfigOut(BaseModel):
    tenant_id: str
    approval_threshold_cents: int
    auto_commit_enabled: bool
    negotiation_mode: NegotiationModeLiteral
    created_at: datetime
    updated_at: datetime


class TenantConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Partial update — any subset of fields.
    approval_threshold_cents: int | None = Field(
        default=None, ge=0, le=10_000_000_000,
        description="Deals at or above this ceiling (in cents) require human approval.",
    )
    auto_commit_enabled: bool | None = None
    negotiation_mode: NegotiationModeLiteral | None = Field(
        default=None,
        description="'ai_first' routes through the Negotiation AI with guardrail retry; "
                    "'deterministic' prices at catalog base_price (emergency kill switch).",
    )
