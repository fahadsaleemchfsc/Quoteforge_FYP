"""
TenantConfig — one row per tenant, stores negotiation policy knobs.

`approval_threshold_cents` is compared against the offer total at accept_offer
time. Deals at or above the threshold route to a human reviewer regardless of
`auto_commit_enabled`. Flipping `auto_commit_enabled` to False forces every
deal through the approval queue — useful during a risk review or while the
team is still calibrating the Negotiation Agent.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base

DEFAULT_APPROVAL_THRESHOLD_CENTS = 5_000_000  # $50,000.00

# Default negotiation mode. "deterministic" leaves the Module 3 AI loop
# disabled (safe default). Admins flip to "ai_first" once a real backend is
# configured. Stored here rather than on GuardrailPolicy because it's an
# operational kill-switch, not a pricing rule.
NEGOTIATION_MODE_DETERMINISTIC = "deterministic"
NEGOTIATION_MODE_AI_FIRST = "ai_first"


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    # PK is also FK: one config row per tenant, cascading delete.
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    approval_threshold_cents = Column(Integer, nullable=False, default=DEFAULT_APPROVAL_THRESHOLD_CENTS)
    auto_commit_enabled = Column(Boolean, nullable=False, default=True)
    negotiation_mode = Column(
        String(20),
        nullable=False,
        default=NEGOTIATION_MODE_DETERMINISTIC,
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
