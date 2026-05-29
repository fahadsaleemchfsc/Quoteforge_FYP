"""Tenant model — the ownership boundary for products, quotes, and replay logs."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, String, func

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
