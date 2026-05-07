"""
Per-tenant atomic counter for document IDs.

One row per tenant. Every request_quote reads+writes via a single
UPDATE ... RETURNING so concurrent callers each get a distinct value and
cannot collide on document_logs.doc_id UNIQUE.

Note on the schema: DocumentLog.doc_id is globally UNIQUE, so for strict
correctness across tenants, bootstrap initializes every tenant's counter
to the global max of existing doc_id numbers (not per-tenant max). In a
single-tenant demo this is a non-issue; multi-tenant correctness is a
schema-level concern (tenant-prefixed doc_id format) left to a later pass.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class DocumentIdCounter(Base):
    __tablename__ = "document_id_counters"

    # Tenant.id (UUID string) — keyed directly to match the existing FK pattern
    # in other per-tenant tables (TenantConfig, GuardrailPolicy).
    tenant_id = Column(String(36), primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
