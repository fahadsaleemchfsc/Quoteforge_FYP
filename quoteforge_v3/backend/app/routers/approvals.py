"""
Admin approval queue router.

Endpoints:
  GET    /api/approvals                 — list with filters + pending_count badge
  GET    /api/approvals/{id}            — full detail including offer payload
  POST   /api/approvals/{id}/approve    — commit via admin (idempotent)
  POST   /api/approvals/{id}/reject     — mark rejected with required notes

Both action endpoints are idempotent: hitting approve twice returns the
already-approved state with idempotent_replay=True and does NOT double-commit.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant, get_current_tenant_id, get_current_user
from app.gateway.adapters.offer_adapter import (
    OfferRejectedError,
    commit_offer,
    mark_approval,
    verify_and_load_offer,
)
from app.gateway.adapters.quote_adapter import load_approval_policy
from app.models.document_log import DocumentLog
from app.models.pending_approval import ApprovalStatus, PendingApproval
from app.models.replay_event import EVENT_BUYER_ROOM_MESSAGE, ReplayEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.approval import (
    ApprovalActionResult,
    ApprovalDetail,
    ApprovalListItem,
    ApprovalListResponse,
    ApproveRequest,
    RejectRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["approvals"])


def _to_list_item(row: PendingApproval, document_id: str, via_buyer_room: bool = False) -> ApprovalListItem:
    return ApprovalListItem(
        id=row.id,
        offer_id=row.offer_id,
        document_id=document_id,
        buyer_agent_id=row.buyer_agent_id,
        offer_total_cents=row.offer_total_cents,
        status=row.status.value,
        created_at=row.created_at,
        expires_at=row.expires_at,
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
        reviewer_notes=row.reviewer_notes,
        via_buyer_room=via_buyer_room,
    )


def _to_detail(row: PendingApproval, document_id: str) -> ApprovalDetail:
    try:
        payload = json.loads(row.offer_payload)
    except json.JSONDecodeError:
        payload = {}
    return ApprovalDetail(
        id=row.id,
        offer_id=row.offer_id,
        document_id=document_id,
        buyer_agent_id=row.buyer_agent_id,
        offer_total_cents=row.offer_total_cents,
        status=row.status.value,
        created_at=row.created_at,
        expires_at=row.expires_at,
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
        reviewer_notes=row.reviewer_notes,
        offer_payload=payload,
    )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant_uuid: str = Depends(get_current_tenant_id),
) -> ApprovalListResponse:
    base = select(PendingApproval).where(PendingApproval.tenant_id == tenant_uuid)
    if status != "all":
        try:
            filter_status = ApprovalStatus(status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"unknown status: {status}") from e
        base = base.where(PendingApproval.status == filter_status)

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    pending_count = (
        await db.execute(
            select(func.count())
            .select_from(PendingApproval)
            .where(
                PendingApproval.tenant_id == tenant_uuid,
                PendingApproval.status == ApprovalStatus.pending,
            )
        )
    ).scalar_one()

    rows_stmt = (
        base.order_by(PendingApproval.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(rows_stmt)).scalars().all()

    # Batch-fetch the corresponding DOC-XXXX identifiers.
    doc_ids: dict[int, str] = {}
    if rows:
        doc_ids_stmt = select(DocumentLog.id, DocumentLog.doc_id).where(
            DocumentLog.id.in_([r.document_log_id for r in rows])
        )
        for pk, doc_id in (await db.execute(doc_ids_stmt)).all():
            doc_ids[pk] = doc_id

    # Batch check: which offers have buyer-room transcripts?
    via_br_set: set[str] = set()
    if rows:
        br_offer_rows = (await db.execute(
            select(ReplayEvent.offer_id).where(
                ReplayEvent.tenant_id == tenant_uuid,
                ReplayEvent.event_type == EVENT_BUYER_ROOM_MESSAGE,
                ReplayEvent.offer_id.in_([r.offer_id for r in rows]),
            ).distinct()
        )).all()
        via_br_set = {oid for (oid,) in br_offer_rows if oid}

    return ApprovalListResponse(
        approvals=[
            _to_list_item(r, doc_ids.get(r.document_log_id, ""),
                          via_buyer_room=r.offer_id in via_br_set)
            for r in rows
        ],
        total=int(total),
        page=page,
        per_page=per_page,
        pending_count=int(pending_count),
    )


@router.get("/{approval_id}/transcript")
async def approval_transcript(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_uuid: str = Depends(get_current_tenant_id),
) -> dict:
    """
    Return the buyer-room chat transcript associated with an approval.
    Empty list if this approval wasn't produced via a share link.
    """
    row = await _load_approval_or_404(db, tenant_uuid, approval_id)

    # session_id is carried in each message's payload.session_id. Look up the
    # session id via a single event tied to this approval's offer_id, then
    # fetch every message for that session.
    offer_event = (await db.execute(
        select(ReplayEvent).where(
            ReplayEvent.tenant_id == tenant_uuid,
            ReplayEvent.event_type == EVENT_BUYER_ROOM_MESSAGE,
            ReplayEvent.offer_id == row.offer_id,
        ).limit(1)
    )).scalar_one_or_none()

    if offer_event is None:
        return {"via_buyer_room": False, "messages": []}

    try:
        session_id = json.loads(offer_event.payload).get("session_id")
    except json.JSONDecodeError:
        session_id = None
    if not session_id:
        return {"via_buyer_room": False, "messages": []}

    principal = f"buyer-room:{session_id}"
    events = (await db.execute(
        select(ReplayEvent).where(
            ReplayEvent.tenant_id == tenant_uuid,
            ReplayEvent.event_type == EVENT_BUYER_ROOM_MESSAGE,
            ReplayEvent.principal_id == principal,
        ).order_by(ReplayEvent.created_at)
    )).scalars().all()

    messages: list[dict] = []
    for e in events:
        try:
            p = json.loads(e.payload)
        except json.JSONDecodeError:
            continue
        messages.append({
            "role": p.get("role"),
            "content": p.get("content", ""),
            "timestamp": e.created_at.isoformat(),
            "tool_calls": p.get("tool_calls", []),
        })
    return {"via_buyer_room": True, "session_id": session_id, "messages": messages}


@router.get("/{approval_id}", response_model=ApprovalDetail)
async def get_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_uuid: str = Depends(get_current_tenant_id),
) -> ApprovalDetail:
    row = (
        await db.execute(
            select(PendingApproval).where(
                PendingApproval.id == approval_id,
                PendingApproval.tenant_id == tenant_uuid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="approval not found")

    doc_row = (
        await db.execute(
            select(DocumentLog.doc_id).where(DocumentLog.id == row.document_log_id)
        )
    ).scalar_one_or_none()
    return _to_detail(row, doc_row or "")


async def _load_approval_or_404(
    db: AsyncSession, tenant_uuid: str, approval_id: str
) -> PendingApproval:
    row = (
        await db.execute(
            select(PendingApproval).where(
                PendingApproval.id == approval_id,
                PendingApproval.tenant_id == tenant_uuid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return row


@router.post("/{approval_id}/approve", response_model=ApprovalActionResult)
async def approve(
    approval_id: str,
    payload: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
) -> ApprovalActionResult:
    tenant_uuid, tenant_slug = tenant.id, tenant.slug
    row = await _load_approval_or_404(db, tenant_uuid, approval_id)

    # Idempotent: already approved → return existing state, do not double-commit.
    if row.status == ApprovalStatus.approved:
        doc_id = (
            await db.execute(
                select(DocumentLog.doc_id).where(DocumentLog.id == row.document_log_id)
            )
        ).scalar_one_or_none() or ""
        return ApprovalActionResult(
            approval=_to_detail(row, doc_id),
            committed_document_id=doc_id,
            idempotent_replay=True,
        )
    if row.status == ApprovalStatus.rejected:
        raise HTTPException(status_code=409, detail="approval already rejected")
    if row.status == ApprovalStatus.expired:
        raise HTTPException(status_code=409, detail="approval has expired")

    # Re-verify the signature stamped at quote time. If an admin's DB was
    # tampered between queue and approve, this refuses to commit.
    stored_sig = await _stored_signature_for_offer(db, row.offer_id)
    if not stored_sig:
        raise HTTPException(status_code=500, detail="stored signature missing for offer")
    fetched = await verify_and_load_offer(
        db,
        tenant_slug=tenant_slug,
        offer_id=row.offer_id,
        signature=stored_sig,
    )

    policy = await load_approval_policy(db, tenant_slug)
    if policy is None:
        raise HTTPException(status_code=500, detail="tenant config unavailable")

    try:
        result = await commit_offer(
            db,
            fetched=fetched,
            tenant_id_uuid=policy.tenant_id,
            buyer_agent_id=row.buyer_agent_id,
            source="admin_approval",
            buyer_reference=None,
        )
    except OfferRejectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    await mark_approval(
        db, approval=row, decision="approved",
        reviewer_user_id=user.id, reviewer_notes=payload.reviewer_notes,
    )
    await db.commit()
    await db.refresh(row)

    logger.info("admin approve: approval=%s doc=%s by=%s", row.id, result.document_id, user.email)
    return ApprovalActionResult(
        approval=_to_detail(row, result.document_id),
        committed_document_id=result.document_id,
        idempotent_replay=result.was_already_committed,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalActionResult)
async def reject(
    approval_id: str,
    payload: RejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_uuid: str = Depends(get_current_tenant_id),
) -> ApprovalActionResult:
    row = await _load_approval_or_404(db, tenant_uuid, approval_id)

    # Idempotent: already rejected → return existing state.
    if row.status == ApprovalStatus.rejected:
        doc_id = (
            await db.execute(
                select(DocumentLog.doc_id).where(DocumentLog.id == row.document_log_id)
            )
        ).scalar_one_or_none() or ""
        return ApprovalActionResult(
            approval=_to_detail(row, doc_id),
            committed_document_id=None,
            idempotent_replay=True,
        )
    if row.status == ApprovalStatus.approved:
        raise HTTPException(status_code=409, detail="approval already approved")
    if row.status == ApprovalStatus.expired:
        raise HTTPException(status_code=409, detail="approval has expired")

    # Mark the draft itself rejected so future accept_offer replays are refused.
    doc = (
        await db.execute(
            select(DocumentLog).where(DocumentLog.id == row.document_log_id)
        )
    ).scalar_one()
    doc.status = "rejected"

    await mark_approval(
        db, approval=row, decision="rejected",
        reviewer_user_id=user.id, reviewer_notes=payload.reviewer_notes,
    )
    await db.commit()
    await db.refresh(row)

    logger.info("admin reject: approval=%s doc=%s by=%s", row.id, doc.doc_id, user.email)
    return ApprovalActionResult(
        approval=_to_detail(row, doc.doc_id),
        committed_document_id=None,
        idempotent_replay=False,
    )


async def _stored_signature_for_offer(db: AsyncSession, offer_id: str) -> str:
    """Look up the signature stamped into DocumentLog.metadata_json at quote time."""
    row = (
        await db.execute(
            select(DocumentLog.metadata_json).where(
                DocumentLog.metadata_json.like(f'%"offer_id": "{offer_id}"%')
            )
        )
    ).scalar_one_or_none()
    if not row:
        return ""
    try:
        meta = json.loads(row)
    except json.JSONDecodeError:
        return ""
    return meta.get("offer_signature", "")
