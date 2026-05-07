"""
Admin negotiations dashboard.

  GET /api/negotiations?outcome=all|first_try|retried|fell_back|timed_out
       &page=1&per_page=50

Groups ReplayEvents of type 'negotiation_attempt' by offer_id, one row per
offer with the full retry chain included so the UI can render the drawer
without a second round-trip.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id
from app.models.replay_event import EVENT_NEGOTIATION_ATTEMPT, ReplayEvent
from app.schemas.negotiation import AttemptOut, NegotiationRow, NegotiationsList

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/negotiations", tags=["negotiations"])


ALLOWED_OUTCOMES = {"all", "first_try", "retried", "fell_back", "timed_out"}


def _classify_outcome(attempts: list[AttemptOut]) -> str:
    if any(a.fell_back for a in attempts):
        return "fell_back"
    if any(a.verdict == "timeout" for a in attempts):
        return "timed_out"
    if len(attempts) > 1:
        return "retried"
    return "first_try"


@router.get("", response_model=NegotiationsList)
async def list_negotiations(
    outcome: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> NegotiationsList:
    if outcome not in ALLOWED_OUTCOMES:
        raise HTTPException(status_code=400, detail=f"unknown outcome: {outcome}")

    # Pull all negotiation_attempt events for this tenant, grouped by offer_id.
    # SQLite performance is fine at ~tens of thousands of rows; when we move to
    # Postgres we'll add an aggregated view.
    stmt = (
        select(ReplayEvent)
        .where(
            ReplayEvent.tenant_id == tenant_id,
            ReplayEvent.event_type == EVENT_NEGOTIATION_ATTEMPT,
        )
        .order_by(ReplayEvent.created_at.desc())
        .limit(5000)        # hard cap — aggregate before serving
    )
    rows = (await db.execute(stmt)).scalars().all()

    grouped: dict[str, list[ReplayEvent]] = defaultdict(list)
    for r in rows:
        if r.offer_id is None:
            continue
        grouped[r.offer_id].append(r)

    # Build NegotiationRow per offer_id.
    negotiations: list[NegotiationRow] = []
    for offer_id, events in grouped.items():
        events.sort(key=lambda e: e.created_at)       # earliest → latest
        attempts: list[AttemptOut] = []
        total_latency = 0
        best_conf: float | None = None
        for e in events:
            try:
                p = json.loads(e.payload)
            except json.JSONDecodeError:
                continue
            a = AttemptOut(
                attempt_number=int(p.get("attempt_number", 0)),
                backend=str(p.get("backend", "")),
                verdict=str(p.get("verdict", "")),
                blocking_check_names=list(p.get("blocking_check_names") or []),
                latency_ms=int(p.get("latency_ms", 0)),
                proposed_lines=p.get("proposed_lines"),
                rationale=p.get("rationale"),
                confidence=p.get("confidence"),
                error=p.get("error"),
                fell_back=bool(p.get("fell_back", False)),
                created_at=e.created_at,
            )
            attempts.append(a)
            total_latency += a.latency_ms
            if a.confidence is not None and (best_conf is None or a.confidence > best_conf):
                best_conf = a.confidence
        if not attempts:
            continue
        # Tiebreak same-millisecond events by the canonical attempt_number.
        attempts.sort(key=lambda a: (a.created_at, a.attempt_number))

        classified = _classify_outcome(attempts)
        negotiations.append(NegotiationRow(
            offer_id=offer_id,
            first_attempt_at=attempts[0].created_at,
            last_attempt_at=attempts[-1].created_at,
            attempt_count=len(attempts),
            final_verdict=attempts[-1].verdict,
            outcome=classified,
            backend=attempts[0].backend,
            best_confidence=best_conf,
            total_latency_ms=total_latency,
            attempts=attempts,
        ))

    # Sort newest-first, filter, paginate.
    negotiations.sort(key=lambda n: n.last_attempt_at, reverse=True)
    if outcome != "all":
        negotiations = [n for n in negotiations if n.outcome == outcome]
    total = len(negotiations)
    start = (page - 1) * per_page
    page_rows = negotiations[start:start + per_page]

    return NegotiationsList(rows=page_rows, total=total, page=page, per_page=per_page)
