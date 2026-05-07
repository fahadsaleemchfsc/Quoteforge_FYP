"""
GuardrailPolicy — per-tenant deterministic validation parameters.

One row per tenant. Read on every request_quote and accept_offer to decide
pass / review / block. All fields are policy values the seller understands;
none of them reach the buyer agent.

`require_approval_above_cents` is the new home for the value previously
stored in TenantConfig.approval_threshold_cents. See app/seed.py for the
one-shot migration that copies old values over.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


# Factory defaults — used when auto-provisioning a new tenant's policy.
DEFAULT_MIN_MARGIN_PERCENT = 15.0
DEFAULT_MAX_DISCOUNT_PERCENT = 20.0
DEFAULT_MAX_DISCOUNT_WITH_APPROVAL_PERCENT = 35.0
DEFAULT_ALLOWED_REGIONS = '["US", "EU", "APAC"]'       # JSON string
DEFAULT_CURRENCY_ALLOWLIST = '["USD"]'
DEFAULT_MIN_DEAL_SIZE_CENTS = 0
DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS = 5_000_000        # $50,000


class GuardrailPolicy(Base):
    __tablename__ = "guardrail_policies"

    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Discount / margin controls.
    min_margin_percent = Column(Numeric(5, 2), nullable=False, default=DEFAULT_MIN_MARGIN_PERCENT)
    max_discount_percent = Column(Numeric(5, 2), nullable=False, default=DEFAULT_MAX_DISCOUNT_PERCENT)
    max_discount_with_approval_percent = Column(
        Numeric(5, 2), nullable=False, default=DEFAULT_MAX_DISCOUNT_WITH_APPROVAL_PERCENT
    )

    # Operating scope.
    allowed_regions = Column(Text, nullable=False, default=DEFAULT_ALLOWED_REGIONS)
    currency_allowlist = Column(Text, nullable=False, default=DEFAULT_CURRENCY_ALLOWLIST)

    # Deal size bounds (cents, ints).
    min_deal_size_cents = Column(Integer, nullable=False, default=DEFAULT_MIN_DEAL_SIZE_CENTS)
    max_deal_size_cents = Column(Integer, nullable=True)

    # Human-approval gate — moved from TenantConfig.approval_threshold_cents.
    require_approval_above_cents = Column(
        Integer, nullable=False, default=DEFAULT_REQUIRE_APPROVAL_ABOVE_CENTS
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
