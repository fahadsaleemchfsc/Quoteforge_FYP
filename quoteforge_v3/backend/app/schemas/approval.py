"""Pydantic schemas for the admin approval queue API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatusLiteral = Literal["pending", "approved", "rejected", "expired"]


class ApprovalListItem(BaseModel):
    """Row shape for the admin queue table."""
    id: str
    offer_id: str
    document_id: str
    buyer_agent_id: str
    offer_total_cents: int
    status: ApprovalStatusLiteral
    created_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: int | None = None
    reviewer_notes: str | None = None
    via_buyer_room: bool = False


class ApprovalDetail(ApprovalListItem):
    """Expanded shape used by the drawer/modal — includes full offer payload."""
    offer_payload: dict[str, Any]


class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalListItem]
    total: int
    page: int
    per_page: int
    pending_count: int = Field(
        description="Total number of pending approvals across all pages — powers the nav badge.",
    )


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_notes: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_notes: str = Field(min_length=1, max_length=2000,
                                description="Reason for rejection — required.")


class ApprovalActionResult(BaseModel):
    approval: ApprovalDetail
    committed_document_id: str | None = Field(
        default=None,
        description="Populated when this action triggered a commit.",
    )
    idempotent_replay: bool = False
