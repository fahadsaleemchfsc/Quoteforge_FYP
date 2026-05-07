"""
Live Agent Feed endpoint.

  GET /api/activity/feed?limit=20

Merges three streams into one timeline the Dashboard polls every 5s:
  - guardrail_evaluation ReplayEvents           → verdict updates
  - negotiation_attempt  ReplayEvents           → retry chain signals
  - AuditLog entries with action IN (offer_committed, offer_queued_for_approval,
    quote_requested, approval_approved, approval_rejected)   → state transitions

Each item is normalized to:
  { timestamp, kind, dot_color, agent, summary, offer_id?, total_cents? }

Newest first. All internal fields stay out (no check_results, no rationale).
Defense demo is about pace + status transitions, not reasoning detail.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id
from app.models.audit_log import AuditLog
from app.models.document_log import DocumentLog
from app.models.replay_event import (
    EVENT_GUARDRAIL_EVALUATION,
    EVENT_NEGOTIATION_ATTEMPT,
    ReplayEvent,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["activity"])


DOT_COLOR = {
    "pass": "green",
    "committed": "green",
    "approved": "green",
    "review": "amber",
    "pending_approval": "amber",
    "queued": "amber",
    "block": "red",
    "rejected": "red",
    "timeout": "gray",
    "backend_error": "orange",
    "parse_error": "orange",
    "default": "gray",
}


def _relabel_action(action: str) -> str:
    return {
        "offer_committed": "committed",
        "offer_queued_for_approval": "queued",
        "approval_approved": "approved",
        "approval_rejected": "rejected",
        "quote_requested": "signed",
    }.get(action, action)


@router.get("/feed")
async def feed(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    items: list[dict[str, Any]] = []

    # Guardrail evaluations
    eval_rows = (await db.execute(
        select(ReplayEvent).where(
            ReplayEvent.tenant_id == tenant_id,
            ReplayEvent.event_type == EVENT_GUARDRAIL_EVALUATION,
            ReplayEvent.created_at >= cutoff,
        ).order_by(ReplayEvent.created_at.desc()).limit(limit * 2)
    )).scalars().all()
    for e in eval_rows:
        try:
            p = json.loads(e.payload)
        except json.JSONDecodeError:
            continue
        verdict = p.get("verdict", "pass")
        snap = p.get("offer_context_snapshot") or {}
        total_cents = snap.get("total_cents")
        summary_bits = [f"guardrail={verdict}"]
        if verdict == "block":
            blocking = [cr["name"] for cr in p.get("check_results", []) if cr.get("verdict") == "block"]
            if blocking:
                summary_bits.append(blocking[0])
        items.append({
            "timestamp": e.created_at.isoformat(),
            "kind": "guardrail",
            "dot_color": DOT_COLOR.get(verdict, DOT_COLOR["default"]),
            "agent": e.principal_id or "",
            "summary": " ".join(summary_bits),
            "offer_id": e.offer_id,
            "total_cents": total_cents,
        })

    # Negotiation attempts
    attempt_rows = (await db.execute(
        select(ReplayEvent).where(
            ReplayEvent.tenant_id == tenant_id,
            ReplayEvent.event_type == EVENT_NEGOTIATION_ATTEMPT,
            ReplayEvent.created_at >= cutoff,
        ).order_by(ReplayEvent.created_at.desc()).limit(limit)
    )).scalars().all()
    for e in attempt_rows:
        try:
            p = json.loads(e.payload)
        except json.JSONDecodeError:
            continue
        verdict = p.get("verdict", "")
        attempt_number = p.get("attempt_number", "?")
        backend = p.get("backend", "")
        summary = f"negotiation {backend} attempt {attempt_number} · {verdict}"
        items.append({
            "timestamp": e.created_at.isoformat(),
            "kind": "negotiation",
            "dot_color": DOT_COLOR.get(verdict, DOT_COLOR["default"]),
            "agent": e.principal_id or "",
            "summary": summary,
            "offer_id": e.offer_id,
            "total_cents": None,
        })

    # AuditLog state transitions
    audit_rows = (await db.execute(
        select(AuditLog).where(
            AuditLog.action.in_([
                "offer_committed",
                "offer_queued_for_approval",
                "approval_approved",
                "approval_rejected",
            ]),
            AuditLog.timestamp >= cutoff,
        ).order_by(AuditLog.timestamp.desc()).limit(limit)
    )).scalars().all()
    for a in audit_rows:
        short = _relabel_action(a.action)
        # Cap long details at 120 chars for the feed row.
        trail = (a.details or "")[:120]
        items.append({
            "timestamp": a.timestamp.isoformat() if a.timestamp else datetime.now(timezone.utc).isoformat(),
            "kind": "state",
            "dot_color": DOT_COLOR.get(short, DOT_COLOR["default"]),
            "agent": (a.user_name or "").replace("mcp:", ""),
            "summary": f"{short} · {trail}",
            "offer_id": a.entity_id,
            "total_cents": None,
        })

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]
