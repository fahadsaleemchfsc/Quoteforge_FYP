"""
PendingApproval — a deal routed to human sign-off at accept_offer time.

The full `offer_payload` is stored here verbatim so the admin UI can render
every line item without joining back to any live catalog state (and so a
replay can be done after the source draft is mutated).

Index on (tenant_id, status) serves the admin queue query pattern — every
page load issues a `WHERE tenant_id = ? AND status = 'pending'`.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class PendingApproval(Base):
    __tablename__ = "pending_approvals"
    __table_args__ = (
        Index("ix_pending_approvals_tenant_status", "tenant_id", "status"),
        Index("ix_pending_approvals_offer", "offer_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offer_id = Column(String(64), nullable=False)
    document_log_id = Column(
        Integer,
        ForeignKey("document_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    buyer_agent_id = Column(String(200), nullable=False)
    offer_total_cents = Column(Integer, nullable=False)
    offer_payload = Column(Text, nullable=False)           # JSON-encoded offer
    status = Column(
        Enum(ApprovalStatus, name="approval_status"),
        nullable=False,
        default=ApprovalStatus.pending,
    )
    reviewer_notes = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    tenant = relationship("Tenant")
    document_log = relationship("DocumentLog")
