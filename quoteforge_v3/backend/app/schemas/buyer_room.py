"""Public schemas for the buyer-room chat API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BuyerRoomContext(BaseModel):
    session_id: str
    seller_name: str
    products: list[dict[str, Any]]
    greeting: str               # the auto-seed opening message


class BuyerRoomMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=4000)


class BuyerRoomMessageResponse(BaseModel):
    assistant_text: str
    offer_state: dict[str, Any] | None = None   # the current offer, if any
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
