"""
CRMSyncJob — queued work item for syncing a committed deal to an external CRM.

Intentionally NOT wired to a worker this session — the worker lands with the
Salesforce end-to-end integration in W4. Rows pile up in status="queued"
until the worker comes online; that's fine, no data is lost.

When the worker does land, it will:
  SELECT * FROM crm_sync_jobs
   WHERE status = 'queued' AND next_attempt_at <= now()
   ORDER BY created_at
   FOR UPDATE SKIP LOCKED  (postgres)
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


class CRMSyncStatus(str, enum.Enum):
    queued = "queued"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    dead_letter = "dead_letter"      # exhausted retries — operator intervention needed


class CRMSyncJob(Base):
    __tablename__ = "crm_sync_jobs"
    __table_args__ = (
        Index("ix_crm_sync_jobs_queue", "status", "next_attempt_at"),
        Index("ix_crm_sync_jobs_tenant", "tenant_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_log_id = Column(
        Integer,
        ForeignKey("document_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_platform = Column(String(50), nullable=False)    # salesforce | hubspot | ...
    payload = Column(Text, nullable=False)                  # JSON-encoded sync payload
    status = Column(
        Enum(CRMSyncStatus, name="crm_sync_status"),
        nullable=False,
        default=CRMSyncStatus.queued,
    )
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    next_attempt_at = Column(DateTime, server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    document_log = relationship("DocumentLog")
