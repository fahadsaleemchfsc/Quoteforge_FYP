"""
Offer adapter — verification, idempotent commit, and human-approval queueing.

This is the seam between the accept_offer MCP tool / admin approval endpoints
and the persistence layer. The tool uses:

  - `verify_and_load_offer(tenant_slug, offer_id, signature)`:
        rejects tampered or foreign offers; returns the stored draft + payload.
  - `commit_offer(fetched, buyer_agent_id, source)`:
        transitions DocumentLog draft → committed, queues a CRM sync job, and
        is idempotent — a committed offer called again returns the original
        receipt.
  - `queue_for_approval(fetched, buyer_agent_id, policy)`:
        creates a PendingApproval row when policy demands human sign-off.
        Idempotent: if a pending row already exists for the same offer_id it
        is returned verbatim rather than duplicated.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.gateway.adapters.quote_adapter import (
    ApprovalPolicy,
    FetchedOffer,
    fetch_offer_by_id,
    verify_offer_signature,
)
from app.gateway.guardrails import GuardrailEngine
from app.gateway.guardrails.builder import from_document_log as build_context_from_doc
from app.gateway.guardrails.engine import EngineResult
from app.gateway.guardrails.policy_loader import load_policy_by_slug
from app.gateway.guardrails.replay import record_evaluation
from app.models.audit_log import AuditLog
from app.models.crm_sync_job import CRMSyncJob, CRMSyncStatus
from app.models.document_log import DocumentLog
from app.models.pending_approval import ApprovalStatus, PendingApproval

logger = logging.getLogger(__name__)


# DocumentLog status values used by this adapter.
STATUS_DRAFT = "draft"
STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_COMMITTED = "committed"
STATUS_REJECTED = "rejected"
STATUS_POLICY_INVALIDATED = "policy_invalidated"

APPROVAL_EXPIRY_HOURS = 48

CommitSource = Literal["agent_gateway", "admin_approval"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class InvalidOfferSignatureError(Exception):
    """HMAC didn't verify — either tampering or wrong signing key."""


class OfferNotFoundError(Exception):
    """No draft persisted under that offer_id for this tenant."""


class OfferExpiredError(Exception):
    """Offer's valid_until has passed."""


class OfferRejectedError(Exception):
    """Offer was previously rejected by a reviewer — cannot be committed."""


class PolicyInvalidatedError(Exception):
    """Offer that was valid at quote time no longer passes the current guardrail policy."""

    def __init__(self, result: EngineResult) -> None:
        super().__init__("policy invalidated")
        self.result = result


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

async def verify_and_load_offer(
    db: AsyncSession,
    *,
    tenant_slug: str,
    offer_id: str,
    signature: str,
) -> FetchedOffer:
    fetched = await fetch_offer_by_id(db, tenant_slug, offer_id)
    if fetched is None:
        raise OfferNotFoundError(offer_id)

    if not verify_offer_signature(fetched.offer_payload, signature):
        raise InvalidOfferSignatureError(offer_id)

    # If we originally signed a different signature, that's also tampering —
    # caller could be replaying a stale token from the same tenant.
    if not verify_offer_signature(fetched.offer_payload, fetched.signature):
        # Stored data is corrupt; treat as not found rather than leak the state.
        logger.error("stored signature no longer verifies offer=%s — data corruption?", offer_id)
        raise OfferNotFoundError(offer_id)

    return fetched


async def re_evaluate_against_policy(
    db: AsyncSession,
    *,
    fetched: FetchedOffer,
    principal_id: str | None,
) -> EngineResult:
    """
    Rebuild OfferContext with fresh product data and re-run the engine.
    Policy or product values may have changed since the quote was issued.

    - verdict=block: caller MUST refuse commit and mark status=policy_invalidated.
    - verdict=review: fine — commit path already handles human routing.
    - verdict=pass: commit.
    """
    loaded = await load_policy_by_slug(db, fetched.tenant_slug)
    if loaded is None:
        raise RuntimeError(f"policy unavailable for tenant {fetched.tenant_slug}")

    offer_context = await build_context_from_doc(db, fetched.document_log)
    if offer_context is None:
        # Corrupt payload — treat as block with a minimal synthetic result.
        # We build a tiny EngineResult so callers see a consistent shape.
        # Safer than silently committing a draft we can't re-materialize.
        from app.gateway.guardrails.engine import CheckResult
        synthetic = EngineResult(
            verdict="block",
            check_results=(CheckResult(
                name="integrity",
                verdict="block",
                reason_internal="offer payload failed to rebuild",
                reason_external="offer cannot be re-evaluated",
            ),),
            policy_snapshot=loaded.snapshot,
        )
        record_evaluation(
            db, tenant_id_uuid=loaded.tenant_id_uuid, result=synthetic,
            offer_id=fetched.offer_payload.get("offer_id"),
            document_log_id=fetched.document_log.id,
            principal_id=principal_id,
            extra={"phase": "accept_offer", "integrity_failure": True},
        )
        return synthetic

    result = GuardrailEngine().evaluate(offer_context, loaded.snapshot)
    record_evaluation(
        db, tenant_id_uuid=loaded.tenant_id_uuid, result=result,
        offer_id=fetched.offer_payload.get("offer_id"),
        document_log_id=fetched.document_log.id,
        principal_id=principal_id,
        extra={"phase": "accept_offer"},
    )
    return result


def ensure_offer_not_expired(fetched: FetchedOffer) -> None:
    valid_until = fetched.document_log.valid_until
    if valid_until is None:
        return
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > valid_until:
        raise OfferExpiredError(fetched.offer_payload.get("offer_id", ""))


# ---------------------------------------------------------------------------
# Commit path
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommitResult:
    document_id: str            # external DOC-XXXX id
    document_log_pk: int        # internal integer pk
    offer_id: str
    total_cents: int
    currency: str
    committed_at: datetime
    was_already_committed: bool = False


async def _enqueue_crm_sync(
    db: AsyncSession,
    *,
    tenant_id: str,
    document_log_id: int,
    offer_payload: dict[str, Any],
) -> None:
    """Register a sync job. Drained by crm_sync_worker on a 15s interval.

    Payload carries everything the worker needs — it does NOT re-query the
    DocumentLog at dispatch time (except for doc_id display in logs), so
    the job is self-describing for replay/debugging.

    `target_platform` derives from whichever CRM is the tenant's "primary"
    — for now that's always Salesforce if connected; multi-CRM selection
    lands when HubSpot parity lands.
    """
    pricing = offer_payload.get("pricing", {}) or {}
    payload = {
        "offer_id": offer_payload.get("offer_id"),
        "doc_id": offer_payload.get("doc_id"),
        "tenant_slug": offer_payload.get("tenant_id"),     # human-readable
        "client_name": offer_payload.get("client_name"),
        "deal_name": offer_payload.get("deal_name") or f"Offer {offer_payload.get('offer_id')}",
        "line_items": offer_payload.get("line_items"),
        "pricing": pricing,
        "contact_email": offer_payload.get("contact_email"),
        "region": offer_payload.get("region"),
        "valid_until": offer_payload.get("valid_until"),
        # Full offer_payload is ALSO on DocumentLog.metadata_json — kept here
        # so the worker can render the PDF without joining back.
        "offer_payload": offer_payload,
    }
    db.add(CRMSyncJob(
        tenant_id=tenant_id,
        document_log_id=document_log_id,
        target_platform="salesforce",        # TODO: choose per tenant when multi-CRM lands
        payload=json.dumps(payload),
        status=CRMSyncStatus.queued,
    ))


async def commit_offer(
    db: AsyncSession,
    *,
    fetched: FetchedOffer,
    tenant_id_uuid: str,
    buyer_agent_id: str,
    source: CommitSource,
    buyer_reference: str | None = None,
) -> CommitResult:
    """
    Idempotent commit. First call transitions draft → committed, queues CRM
    sync, writes a Replay Layer entry. Subsequent calls on the same offer_id
    short-circuit and return the original receipt.
    """
    doc = fetched.document_log
    offer_id = fetched.offer_payload["offer_id"]
    pricing = fetched.offer_payload["pricing"]
    currency: str = pricing["currency"]
    total_cents: int = int(pricing["total_cents"])

    if doc.status == STATUS_COMMITTED:
        logger.info("commit_offer: offer=%s already committed — idempotent return", offer_id)
        return CommitResult(
            document_id=doc.doc_id,
            document_log_pk=doc.id,
            offer_id=offer_id,
            total_cents=total_cents,
            currency=currency,
            committed_at=doc.delivered_at or doc.generated_at or datetime.now(timezone.utc),
            was_already_committed=True,
        )

    if doc.status == STATUS_REJECTED:
        raise OfferRejectedError(offer_id)

    now = datetime.now(timezone.utc)
    doc.status = STATUS_COMMITTED
    doc.delivery_status = "pending_crm_sync"
    doc.delivered_at = now

    # PDF generation deliberately stubbed this session — the existing renderer
    # requires AI-generated sections, which is a heavy synchronous call we're
    # not making on the commit hot-path. The Dual Output Renderer (Module 4)
    # will render offer_payload → PDF on demand instead.
    # TODO(module-4): attach rendered PDF here and set doc.file_path.

    # Merge buyer_reference into the existing metadata blob.
    try:
        meta = json.loads(doc.metadata_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    commit_record: dict[str, Any] = {
        "committed_at": now.isoformat(),
        "committed_via": source,
        "buyer_agent_id": buyer_agent_id,
    }
    if buyer_reference:
        commit_record["buyer_reference"] = buyer_reference
    meta["commit"] = commit_record
    doc.metadata_json = json.dumps(meta)

    await _enqueue_crm_sync(
        db,
        tenant_id=tenant_id_uuid,
        document_log_id=doc.id,
        offer_payload=fetched.offer_payload,
    )

    db.add(AuditLog(
        user_id=None,
        user_name=f"mcp:{buyer_agent_id}",
        action="offer_committed",
        entity_type="offer",
        entity_id=offer_id,
        details=(
            f"doc={doc.doc_id} tenant={fetched.tenant_slug} "
            f"total={total_cents / 100:.2f} {currency} via={source}"
        ),
    ))

    logger.info(
        "commit_offer: offer=%s doc=%s tenant=%s buyer=%s source=%s total_cents=%d",
        offer_id, doc.doc_id, fetched.tenant_slug, buyer_agent_id, source, total_cents,
    )

    return CommitResult(
        document_id=doc.doc_id,
        document_log_pk=doc.id,
        offer_id=offer_id,
        total_cents=total_cents,
        currency=currency,
        committed_at=now,
    )


# ---------------------------------------------------------------------------
# Approval-queue path
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QueuedApproval:
    approval_id: str
    offer_id: str
    expires_at: datetime
    status: ApprovalStatus
    was_already_queued: bool = False


async def queue_for_approval(
    db: AsyncSession,
    *,
    fetched: FetchedOffer,
    tenant_id_uuid: str,
    buyer_agent_id: str,
) -> QueuedApproval:
    """Idempotent: existing pending row for this offer_id is returned as-is."""
    doc = fetched.document_log
    offer_id = fetched.offer_payload["offer_id"]
    total_cents = int(fetched.offer_payload["pricing"]["total_cents"])

    existing = (
        await db.execute(
            select(PendingApproval).where(PendingApproval.offer_id == offer_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return QueuedApproval(
            approval_id=existing.id,
            offer_id=offer_id,
            expires_at=existing.expires_at,
            status=existing.status,
            was_already_queued=True,
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=APPROVAL_EXPIRY_HOURS)

    approval = PendingApproval(
        tenant_id=tenant_id_uuid,
        offer_id=offer_id,
        document_log_id=doc.id,
        buyer_agent_id=buyer_agent_id,
        offer_total_cents=total_cents,
        offer_payload=json.dumps(fetched.offer_payload),
        status=ApprovalStatus.pending,
        expires_at=expires_at,
    )
    db.add(approval)

    # Keep the draft's status in lock-step so the admin table and the buyer
    # agent see the same state.
    doc.status = STATUS_PENDING_APPROVAL

    try:
        await db.flush()
    except IntegrityError:
        # Race: another request inserted the row between our check and insert.
        await db.rollback()
        existing = (
            await db.execute(
                select(PendingApproval).where(PendingApproval.offer_id == offer_id)
            )
        ).scalar_one()
        return QueuedApproval(
            approval_id=existing.id,
            offer_id=offer_id,
            expires_at=existing.expires_at,
            status=existing.status,
            was_already_queued=True,
        )

    db.add(AuditLog(
        user_id=None,
        user_name=f"mcp:{buyer_agent_id}",
        action="offer_queued_for_approval",
        entity_type="offer",
        entity_id=offer_id,
        details=(
            f"approval_id={approval.id} doc={doc.doc_id} "
            f"tenant={fetched.tenant_slug} total={total_cents / 100:.2f} "
            f"{fetched.offer_payload['pricing']['currency']}"
        ),
    ))

    logger.info(
        "queue_for_approval: offer=%s approval=%s doc=%s tenant=%s",
        offer_id, approval.id, doc.doc_id, fetched.tenant_slug,
    )
    return QueuedApproval(
        approval_id=approval.id,
        offer_id=offer_id,
        expires_at=expires_at,
        status=ApprovalStatus.pending,
    )


# ---------------------------------------------------------------------------
# Convenience used by both accept_offer and the admin approval endpoints
# ---------------------------------------------------------------------------

async def mark_approval(
    db: AsyncSession,
    *,
    approval: PendingApproval,
    decision: Literal["approved", "rejected"],
    reviewer_user_id: int,
    reviewer_notes: str | None,
) -> None:
    approval.status = (
        ApprovalStatus.approved if decision == "approved" else ApprovalStatus.rejected
    )
    approval.reviewer_notes = reviewer_notes
    approval.reviewed_by = reviewer_user_id
    approval.reviewed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=reviewer_user_id,
        user_name=f"user:{reviewer_user_id}",
        action=f"approval_{decision}",
        entity_type="pending_approval",
        entity_id=approval.id,
        details=(
            f"offer={approval.offer_id} total={approval.offer_total_cents / 100:.2f} "
            f"notes={(reviewer_notes or '').strip()[:200]}"
        ),
    ))
