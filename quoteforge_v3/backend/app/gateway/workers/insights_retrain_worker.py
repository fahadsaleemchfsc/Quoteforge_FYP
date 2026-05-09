"""
Nightly retraining worker for Deal Insights (Module 6).

Demo-path: runs once a day at 02:00 UTC. For each tenant that has an active
model, it counts closed Opportunities visible through the saved mapping,
compares against the training_rows of the active model, and triggers a retrain
if the growth ≥ RETRAIN_ROW_DELTA.

Not production-hardened (by design — see README "Demo-path disclaimers"):
  - No retry / backoff if training fails
  - No cross-tenant concurrency lock (training is sequential per tick)
  - No rollback if a new model is worse than the previous

When a new model version lands, cached predictions for the superseded version
are deleted so the next /predict call re-scores against the new model.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.insights import (
    DealInsightMapping,
    DealInsightModel,
    DealInsightPrediction,
)
from app.services.insights.salesforce_fetch import fetch_closed_opportunities
from app.services.insights.trainer import (
    _mapping_to_bundle,
    train_model_for_tenant,
)

logger = logging.getLogger(__name__)

RETRAIN_ROW_DELTA = 20     # trigger retrain when closed-Opp count has grown by this many
RETRAIN_HOUR_UTC = 2       # 02:00 UTC nightly

_scheduler: AsyncIOScheduler | None = None


async def run_retrain_pass() -> None:
    """One tick of the retrain worker. Safe to call manually from tests."""
    async with async_session() as db:
        tenants_with_active = await _tenants_needing_check(db)

    for tenant_id in tenants_with_active:
        try:
            await _maybe_retrain(tenant_id)
        except Exception as e:
            # Demo-path: log + continue. No dead-letter or retry queue.
            logger.exception(
                "insights_retrain: tenant=%s failed during retrain check: %s",
                tenant_id, e,
            )


async def _tenants_needing_check(db: AsyncSession) -> list[str]:
    """Tenants with an active model AND a saved mapping."""
    res = await db.execute(
        select(DealInsightModel.tenant_id)
        .where(DealInsightModel.is_active.is_(True))
        .distinct()
    )
    tenant_ids = [row for row in res.scalars().all() if row]
    # Further filter to those with a mapping (required for fetch).
    kept: list[str] = []
    for tid in tenant_ids:
        mapping_res = await db.execute(
            select(DealInsightMapping.id).where(DealInsightMapping.tenant_id == tid)
        )
        if mapping_res.scalar_one_or_none() is not None:
            kept.append(tid)
    return kept


async def _maybe_retrain(tenant_id: str) -> None:
    async with async_session() as db:
        mapping_res = await db.execute(
            select(DealInsightMapping).where(DealInsightMapping.tenant_id == tenant_id)
        )
        mapping = mapping_res.scalar_one_or_none()

        active_res = await db.execute(
            select(DealInsightModel)
            .where(
                DealInsightModel.tenant_id == tenant_id,
                DealInsightModel.is_active.is_(True),
            )
            .order_by(DealInsightModel.version.desc())
        )
        active = active_res.scalars().first()

    if mapping is None or active is None:
        return

    bundle = _mapping_to_bundle(mapping)
    excluded_rt = mapping.excluded_record_types_list

    # Cheap growth probe: fetch closed Opps and compare count. We accept the
    # cost of pulling the training set because (a) it's once per night and
    # (b) we'd need to pull it anyway to retrain.
    try:
        opps = await fetch_closed_opportunities(
            tenant_id=tenant_id, mapping=bundle,
            excluded_record_types=excluded_rt,
        )
    except Exception as e:
        logger.info(
            "insights_retrain: tenant=%s probe failed (%s) — skipping this cycle",
            tenant_id, e,
        )
        return

    growth = len(opps) - active.training_rows
    if growth < RETRAIN_ROW_DELTA:
        logger.debug(
            "insights_retrain: tenant=%s growth=%d < threshold=%d — skip",
            tenant_id, growth, RETRAIN_ROW_DELTA,
        )
        return

    logger.info(
        "insights_retrain: tenant=%s growth=%d rows ≥ %d — training new model",
        tenant_id, growth, RETRAIN_ROW_DELTA,
    )
    new_model = await train_model_for_tenant(tenant_id)

    # Invalidate stale predictions for all prior model versions.
    async with async_session() as db:
        await db.execute(
            delete(DealInsightPrediction).where(
                DealInsightPrediction.tenant_id == tenant_id,
                DealInsightPrediction.model_version != new_model.version,
            )
        )
        await db.commit()

    logger.info(
        "insights_retrain: tenant=%s new version=%d auc=%.3f",
        tenant_id, new_model.version, new_model.auc,
    )


# ─── Lifecycle ───────────────────────────────────────────────────

def start_retrain_scheduler() -> None:
    """Called from main lifespan. No-op if already running.

    Honors INSIGHTS_TRAIN_DISABLED=true as a kill switch — when set, the
    nightly cron is not registered. Use during defense windows or any
    period where surprise retrains would be disruptive. Manual training
    paths (POST /api/insights/train, the admin portal training wizard)
    are NOT gated by this flag — by design, those are intentional.
    """
    if os.environ.get("INSIGHTS_TRAIN_DISABLED", "").lower() in ("1", "true", "yes"):
        logger.info(
            "insights_retrain_worker: nightly cron disabled via "
            "INSIGHTS_TRAIN_DISABLED env var",
        )
        return
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        run_retrain_pass,
        trigger="cron",
        hour=RETRAIN_HOUR_UTC,
        minute=0,
        id="insights_retrain_nightly",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "insights_retrain_worker: scheduler started (cron %02d:00 UTC)",
        RETRAIN_HOUR_UTC,
    )


def stop_retrain_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("insights_retrain_worker: scheduler stopped")
