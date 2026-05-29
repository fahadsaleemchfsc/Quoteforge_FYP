"""
DealShareToken — a public URL a seller generates and sends to a human buyer.

The buyer hits /buy/{token} and talks to the Claude-mediated negotiation
assistant. The token:
  - scopes the session to one tenant's catalog + policy
  - has a 7-day expiry
  - tracks last_used_at so admins can see which links went nowhere

NOT an auth token — no PII attached, no privileges beyond the tenant's
agent-exposed catalog. Safe to share by link.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class DealShareToken(Base):
    __tablename__ = "deal_share_tokens"
    __table_args__ = (
        Index("ix_deal_share_tokens_tenant_expires", "seller_tenant_id", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    token = Column(String(48), unique=True, nullable=False, index=True)
    seller_tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    label = Column(String(200), nullable=False, default="Buyer quote request")

    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
