"""
Replay Layer writer — persists engine evaluations as structured rows.

Uses the ReplayEvent model so we can query by verdict / event_type / tenant
without parsing free-text AuditLog details. Callers hold the session; we add
the row but don't commit — the enclosing request transaction decides that.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.guardrails.engine import EngineResult
from app.models.replay_event import (
    EVENT_GUARDRAIL_EVALUATION,
    EVENT_GUARDRAIL_SIMULATION,
    EVENT_NEGOTIATION_ATTEMPT,
    ReplayEvent,
)


def record_negotiation_attempt(
    db: AsyncSession,
    *,
    tenant_id_uuid: str,
    offer_id: str | None,
    principal_id: str | None,
    attempt_number: int,
    backend: str,
    verdict: str,
    blocking_check_names: tuple[str, ...] = (),
    latency_ms: int = 0,
    proposed_lines: list[dict[str, Any]] | None = None,
    rationale: str | None = None,
    confidence: float | None = None,
    raw_model_output: str | None = None,
    error: str | None = None,
    fell_back: bool = False,
) -> None:
    """Persist one Negotiation AI attempt. Stored so the admin dashboard can
    reconstruct the retry chain per offer."""
    payload: dict[str, Any] = {
        "attempt_number": attempt_number,
        "backend": backend,
        "verdict": verdict,
        "blocking_check_names": list(blocking_check_names),
        "latency_ms": latency_ms,
        "fell_back": fell_back,
    }
    if proposed_lines is not None:
        payload["proposed_lines"] = proposed_lines
    if rationale is not None:
        payload["rationale"] = rationale
    if confidence is not None:
        payload["confidence"] = confidence
    if raw_model_output is not None:
        payload["raw_model_output"] = raw_model_output[:4000]     # cap blob size
    if error is not None:
        payload["error"] = error
    db.add(ReplayEvent(
        tenant_id=tenant_id_uuid,
        event_type=EVENT_NEGOTIATION_ATTEMPT,
        offer_id=offer_id,
        document_log_id=None,
        principal_id=principal_id,
        payload=json.dumps(payload, default=str),
    ))


def record_evaluation(
    db: AsyncSession,
    *,
    tenant_id_uuid: str,
    result: EngineResult,
    offer_id: str | None,
    document_log_id: int | None,
    principal_id: str | None,
    extra: dict[str, Any] | None = None,
    simulation: bool = False,
) -> None:
    payload = result.to_replay_dict()
    if extra:
        payload["extra"] = extra
    db.add(ReplayEvent(
        tenant_id=tenant_id_uuid,
        event_type=EVENT_GUARDRAIL_SIMULATION if simulation else EVENT_GUARDRAIL_EVALUATION,
        offer_id=offer_id,
        document_log_id=document_log_id,
        principal_id=principal_id,
        payload=json.dumps(payload, default=str),
    ))
