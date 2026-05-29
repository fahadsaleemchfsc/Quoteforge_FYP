"""Product model — the authoritative catalog.

`min_price_floor` is the hard floor the Negotiation Agent (Module 3) can never
undercut when counter-offering. Never surfaced to buyer agents.

`agent_exposed` gates visibility from the MCP `get_products` tool. Sellers have
to explicitly opt-in per product — default is False so nothing leaks.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        Index("ix_products_tenant_exposed", "tenant_id", "agent_exposed"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)

    base_price = Column(Numeric(12, 2), nullable=False)
    min_price_floor = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    unit = Column(String(50), nullable=False, default="license")

    agent_exposed = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
