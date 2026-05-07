"""Admin schemas for share tokens."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ShareTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="Buyer quote request", min_length=1, max_length=200)
    expires_in_days: int = Field(default=7, ge=1, le=90)


class ShareTokenOut(BaseModel):
    id: str
    token: str
    label: str
    share_url: str                # fully-resolved public URL the seller can copy
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None


class ShareTokenList(BaseModel):
    tokens: list[ShareTokenOut]
