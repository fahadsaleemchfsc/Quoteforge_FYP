"""
ReplayEvent — structured Replay Layer entries.

Sits alongside AuditLog (which stays as the general-purpose, free-text log).
ReplayEvent is for events we want to query and aggregate — the first citizen
is guardrail evaluations, where we store the full check breakdown plus a
snapshot of the policy at evaluation time so replays are accurate even after
the policy changes.

The `payload` column holds JSON-encoded structure; schema is event-type-
specific. This keeps the table flexible without going full EAV.
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
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


# Event types (string constants for stability across refactors).
EVENT_GUARDRAIL_EVALUATION = "guardrail_evaluation"
EVENT_GUARDRAIL_SIMULATION = "guardrail_simulation"
EVENT_NEGOTIATION_ATTEMPT = "negotiation_attempt"
EVENT_BUYER_ROOM_MESSAGE = "buyer_room_message"
EVENT_CRM_SYNC = "crm_sync"


class ReplayEvent(Base):
    __tablename__ = "replay_events"
    __table_args__ = (
        Index("ix_replay_events_tenant_type_created", "tenant_id", "event_type", "created_at"),
        Index("ix_replay_events_offer", "offer_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)

    # Correlation fields — nullable because not every event has all three.
    offer_id = Column(String(64), nullable=True)
    document_log_id = Column(Integer, ForeignKey("document_logs.id", ondelete="SET NULL"), nullable=True)
    principal_id = Column(String(200), nullable=True)

    # Event-type-specific JSON body (e.g. verdict, check_results, policy_snapshot).
    payload = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    document_log = relationship("DocumentLog")
