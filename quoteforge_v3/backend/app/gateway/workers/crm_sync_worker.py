"""
CRM sync worker.

APScheduler polls every WORKER_INTERVAL_SECONDS. Each tick:
  1. SELECT up to BATCH_SIZE CRMSyncJob rows where status in ('queued', 'failed')
     AND next_attempt_at <= now() AND attempts < MAX_ATTEMPTS.
  2. For each job: flip status='in_progress', dispatch to the right connector,
     on success set status='completed', on failure set status='failed' with
     exponential backoff on next_attempt_at.
  3. After MAX_ATTEMPTS failures: status='dead_letter' — operator-visible.

Concurrency:
  An asyncio.Lock prevents a second tick from starting before the first
  finishes. Sufficient for single-process deployment. Multi-process would
  need `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres) — flagged as future
  work.

Every transition writes an EVENT_CRM_SYNC ReplayEvent so admins can replay.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.gateway.rendering import OfferRenderer
from app.models.crm_connection import CRMConnection
from app.models.crm_sync_job import CRMSyncJob, CRMSyncStatus
from app.models.document_log import DocumentLog
from app.models.replay_event import EVENT_CRM_SYNC, ReplayEvent
from app.services.salesforce_connector import get_refresh_aware_client

logger = logging.getLogger(__name__)

WORKER_INTERVAL_SECONDS = 15
BATCH_SIZE = 10
MAX_ATTEMPTS = 5

_tick_lock = asyncio.Lock()
_scheduler: AsyncIOScheduler | None = None


def _backoff_seconds(attempt: int) -> int:
    """Exponential backoff: 2^attempt minutes, capped at 30 minutes."""
    return min(30, 2 ** attempt) * 60


async def _log_event(
    db: AsyncSession, *, tenant_id: str, job_id: str, offer_id: str | None,
    status: str, detail: dict[str, Any],
) -> None:
    db.add(ReplayEvent(
        tenant_id=tenant_id,
        event_type=EVENT_CRM_SYNC,
        offer_id=offer_id,
        document_log_id=None,
        principal_id="worker:crm_sync",
        payload=json.dumps({"job_id": job_id, "status": status, "detail": detail}, default=str),
    ))


async def _select_next_batch(db: AsyncSession) -> list[CRMSyncJob]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(CRMSyncJob)
        .where(
            CRMSyncJob.status.in_((CRMSyncStatus.queued, CRMSyncStatus.failed)),
            CRMSyncJob.attempts < MAX_ATTEMPTS,
            CRMSyncJob.next_attempt_at <= now,
        )
        .order_by(CRMSyncJob.next_attempt_at)
        .limit(BATCH_SIZE)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _mark_in_progress(db: AsyncSession, job: CRMSyncJob) -> None:
    job.status = CRMSyncStatus.in_progress
    job.attempts += 1
    await db.flush()


async def _mark_success(
    db: AsyncSession, job: CRMSyncJob, external_id: str | None, doc_log_id: int,
) -> None:
    job.status = CRMSyncStatus.completed
    job.last_error = None
    # Bookkeeping on DocumentLog so the admin UI can show sync state.
    doc = (await db.execute(select(DocumentLog).where(DocumentLog.id == doc_log_id))).scalar_one_or_none()
    if doc is not None:
        doc.crm_synced_at = datetime.now(timezone.utc)
        if external_id:
            doc.crm_external_id = external_id
    await db.flush()


async def _mark_failure(db: AsyncSession, job: CRMSyncJob, error: str) -> None:
    job.last_error = error[:2000]
    if job.attempts >= MAX_ATTEMPTS:
        job.status = CRMSyncStatus.dead_letter
    else:
        job.status = CRMSyncStatus.failed
        job.next_attempt_at = datetime.now(timezone.utc) + timedelta(
            seconds=_backoff_seconds(job.attempts)
        )
    await db.flush()


# ---------------------------------------------------------------------------
# Salesforce dispatch
# ---------------------------------------------------------------------------

async def _dispatch_salesforce(
    db: AsyncSession, job: CRMSyncJob, payload: dict,
) -> dict:
    """
    Sync one queued offer to Salesforce:
      1. Resolve the tenant's active Salesforce CRMConnection.
      2. Render the offer PDF on-demand via OfferRenderer to a temp file.
      3. Create (or resolve) an Opportunity. If payload.deal_id looks like a
         SF Opportunity Id (starts with 006), use it; otherwise create fresh.
      4. Call create_quoteforge_document to upload + link + log.
      5. Return {external_id, opportunity_id, pdf_bytes_len}.
    Raises on any failure — caller records it against the job.
    """
    # 1. Active SF connection
    conn_row = (await db.execute(
        select(CRMConnection).where(
            CRMConnection.platform == "Salesforce",
            CRMConnection.status == "connected",
        ).limit(1)
    )).scalar_one_or_none()
    if conn_row is None:
        raise RuntimeError("no connected Salesforce connection for tenant")

    client = await get_refresh_aware_client(db, conn_row.id)
    if client is None:
        raise RuntimeError("failed to construct Salesforce client (bad tokens?)")

    # 2. Render PDF to a temp path (create_quoteforge_document takes a file path).
    offer_payload = payload.get("offer_payload", {})
    # Inject the stored signature into the payload so the renderer shows it.
    doc_log_id = job.document_log_id
    doc = (await db.execute(
        select(DocumentLog).where(DocumentLog.id == doc_log_id)
    )).scalar_one_or_none()
    if doc is not None:
        try:
            meta = json.loads(doc.metadata_json or "{}")
            offer_payload.setdefault("__signature__", meta.get("offer_signature", ""))
        except json.JSONDecodeError:
            pass
    pdf_bytes = OfferRenderer().render_pdf(offer_payload, tenant_name="QuoteForge")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(pdf_bytes)
    tmp.close()

    try:
        # 3. Opportunity — reuse if deal_id looks like a SF Id (starts with 006).
        opp_id = None
        orig_deal_id = (offer_payload.get("deal_id") or "").strip()
        if orig_deal_id.startswith("006") and len(orig_deal_id) in (15, 18):
            opp_id = orig_deal_id
        else:
            opp_resp = await client.create_opportunity_with_line_items(
                account_name=payload.get("client_name") or "Unknown Buyer",
                deal_name=payload.get("deal_name") or f"QF {payload.get('offer_id')}",
                amount=float(payload.get("pricing", {}).get("total", 0)),
                close_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                stage="Closed Won",
            )
            opp_id = opp_resp.get("opportunity_id")
            if not opp_id:
                raise RuntimeError(f"failed to create Opportunity: {opp_resp}")

        # 4. Upload + link + log — existing connector method.
        doc_resp = await client.create_quoteforge_document(
            opportunity_id=opp_id,
            file_path=tmp.name,
            doc_metadata={
                "doc_id": payload.get("doc_id"),
                "offer_id": payload.get("offer_id"),
                "client": payload.get("client_name"),
                "deal_name": payload.get("deal_name"),
                "amount": float(payload.get("pricing", {}).get("total", 0)),
                "status": "generated",
            },
        )
        if "error" in doc_resp:
            raise RuntimeError(f"document push failed: {doc_resp['error']}")

        return {
            "external_id": doc_resp.get("quoteforge_document_id") or doc_resp.get("content_version_id"),
            "opportunity_id": opp_id,
            "pdf_bytes_len": len(pdf_bytes),
            "sf_response": doc_resp,
        }
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

async def process_crm_sync_jobs() -> dict[str, int]:
    """Drain one batch. Returns per-status counts for observability / tests."""
    if _tick_lock.locked():
        logger.debug("crm_sync_worker: previous tick still running, skipping")
        return {"skipped": 1}

    async with _tick_lock:
        processed = {"attempted": 0, "completed": 0, "failed": 0, "dead_letter": 0}
        async with async_session() as db:
            batch = await _select_next_batch(db)
            if not batch:
                return processed
            logger.info("crm_sync_worker: dispatching %d job(s)", len(batch))
            for job in batch:
                await _mark_in_progress(db, job)
                await db.commit()

                try:
                    payload = json.loads(job.payload or "{}")
                except json.JSONDecodeError as e:
                    async with async_session() as db2:
                        fresh = (await db2.execute(
                            select(CRMSyncJob).where(CRMSyncJob.id == job.id)
                        )).scalar_one()
                        await _mark_failure(db2, fresh, f"payload malformed: {e}")
                        await _log_event(db2, tenant_id=fresh.tenant_id, job_id=fresh.id,
                                         offer_id=None, status=fresh.status.value,
                                         detail={"error": str(e)})
                        await db2.commit()
                    processed["failed"] += 1
                    continue

                processed["attempted"] += 1
                try:
                    if job.target_platform == "salesforce":
                        result = await _dispatch_salesforce(db, job, payload)
                    else:
                        raise RuntimeError(f"unsupported target_platform: {job.target_platform}")

                    async with async_session() as db2:
                        fresh = (await db2.execute(
                            select(CRMSyncJob).where(CRMSyncJob.id == job.id)
                        )).scalar_one()
                        await _mark_success(db2, fresh, result.get("external_id"), job.document_log_id)
                        await _log_event(
                            db2, tenant_id=fresh.tenant_id, job_id=fresh.id,
                            offer_id=payload.get("offer_id"),
                            status="completed", detail=result,
                        )
                        await db2.commit()
                    processed["completed"] += 1
                except Exception as e:   # noqa: BLE001 — surface cleanly into the job row
                    async with async_session() as db2:
                        fresh = (await db2.execute(
                            select(CRMSyncJob).where(CRMSyncJob.id == job.id)
                        )).scalar_one()
                        await _mark_failure(db2, fresh, f"{type(e).__name__}: {e}")
                        await _log_event(
                            db2, tenant_id=fresh.tenant_id, job_id=fresh.id,
                            offer_id=payload.get("offer_id"),
                            status=fresh.status.value, detail={"error": str(e)[:400]},
                        )
                        await db2.commit()
                    if fresh.status == CRMSyncStatus.dead_letter:
                        processed["dead_letter"] += 1
                        logger.error("crm_sync_worker: job %s dead-lettered: %s", job.id, e)
                    else:
                        processed["failed"] += 1
                        logger.warning("crm_sync_worker: job %s failed (attempt %d/%d): %s",
                                       job.id, fresh.attempts, MAX_ATTEMPTS, e)
        return processed


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        process_crm_sync_jobs,
        trigger="interval",
        seconds=WORKER_INTERVAL_SECONDS,
        id="crm_sync_drain",
        max_instances=1,          # belt-and-suspenders alongside _tick_lock
        coalesce=True,
    )
    _scheduler.start()
    logger.info("crm_sync_worker: scheduler started (interval=%ds)", WORKER_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("crm_sync_worker: scheduler stopped")
