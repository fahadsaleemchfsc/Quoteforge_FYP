"""
Trainer — LightGBM per-tenant win-probability classifier.

Train happens on closed Opportunities only (IsClosed=TRUE). For each closed
row we know the outcome (IsWon) — that's the label. Prediction later runs
the same feature pipeline against open Opps and asks the model how likely
they are to close won.

Minimum viable training set:
    - 50 closed Opps total
    - 10 closed-won
    - 10 closed-lost
Below these thresholds the caller gets InsufficientDataError with a message
that's safe to render in the admin UI.

Training runs in a background task (see router.trigger_training). A tenant-
scoped in-memory status dict tracks progress so /status can tell the UI
whether it's "idle | training | done | error" without introducing a second
table for job tracking.
"""
from __future__ import annotations

import asyncio
import logging
import os
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.insights import DealInsightMapping, DealInsightModel
from app.services.insights.features import (
    CATEGORICAL_BASE_COLS,
    MappingBundle,
    NUMERIC_BASE_COLS,
    build_feature_frame,
    one_hot_and_align,
    targets_from_records,
)
from app.services.insights.salesforce_fetch import (
    fetch_activities_for_opportunities,
    fetch_closed_opportunities,
)

logger = logging.getLogger(__name__)

# Session 6.5 — four-tier minimum-data gate. Below the hard floor we refuse
# to train at all; above it, tier determines how the UI talks about model
# reliability (confidence ranges vs. point estimates, retrain urgency).
MIN_DEALS_HARD_FLOOR = 100
MIN_DEALS_EARLY_STAGE = 300
MIN_DEALS_STANDARD = 1000
MIN_WINS = 10
MIN_LOSSES = 10

# Legacy alias kept for any external callers that import MIN_TOTAL_ROWS.
MIN_TOTAL_ROWS = MIN_DEALS_HARD_FLOOR


def classify_data_quality_tier(n: int) -> str:
    """Bucket training-row count into the rep-facing reliability tier."""
    if n < MIN_DEALS_HARD_FLOOR:
        return "insufficient"
    if n < MIN_DEALS_EARLY_STAGE:
        return "early_stage"
    if n < MIN_DEALS_STANDARD:
        return "standard"
    return "mature"

MODEL_STORAGE_ROOT = os.environ.get(
    "INSIGHTS_MODEL_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                 "storage", "insights_models"),
)


class InsightsTrainingError(Exception):
    """Base class for trainer errors that should surface in the API."""

    def __init__(self, message: str, *, code: str = "training_error") -> None:
        super().__init__(message)
        self.code = code


class InsufficientDataError(InsightsTrainingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="insufficient_data")


class UnsupportedDataError(InsightsTrainingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="unsupported_data")


# ─── Job status tracker (in-memory) ─────────────────────────────────
# Demo-path: single-process only. Multi-process deployments would back this
# with Redis or a DB row. Phase 2 item.

@dataclass
class TrainingJobStatus:
    job_id: str
    tenant_id: str
    state: str = "idle"           # idle | running | done | error
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str = ""
    error_code: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


_job_registry: dict[str, TrainingJobStatus] = {}
_job_by_tenant: dict[str, str] = {}   # latest job_id per tenant


def register_job(tenant_id: str) -> TrainingJobStatus:
    import uuid
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    status = TrainingJobStatus(
        job_id=job_id, tenant_id=tenant_id,
        state="running", started_at=datetime.now(timezone.utc),
        message="initializing",
    )
    _job_registry[job_id] = status
    _job_by_tenant[tenant_id] = job_id
    return status


def get_job(job_id: str) -> TrainingJobStatus | None:
    return _job_registry.get(job_id)


def get_latest_job_for_tenant(tenant_id: str) -> TrainingJobStatus | None:
    job_id = _job_by_tenant.get(tenant_id)
    return _job_registry.get(job_id) if job_id else None


# ─── Entry point (foreground helper + async background wrapper) ──────

async def train_model_for_tenant(tenant_id: str) -> DealInsightModel:
    """Train a new model + persist metadata. Runs synchronously from the caller's
    perspective — the router wraps this in asyncio.create_task for background
    execution. Every major step is logged to the tenant's training_log.txt
    (tail-able during the defense demo).
    """
    from app.services.insights.training_log import TrainingLogger

    started = time.perf_counter()
    with TrainingLogger(tenant_id) as log:
        log.info("training started")
        async with async_session() as db:
            mapping_row = await _load_mapping(db, tenant_id)
            if mapping_row is None:
                raise InsightsTrainingError(
                    "Mapping not configured — complete the Deal Insights setup wizard first.",
                    code="mapping_missing",
                )
            bundle = _mapping_to_bundle(mapping_row)
            excluded_rt = mapping_row.excluded_record_types_list
        log.info(f"mapping loaded · custom_fields={len(bundle.custom_fields)}")

        # Fetch training data (SF I/O + synthetic fallback for dev).
        opportunities = await fetch_closed_opportunities(
            tenant_id=tenant_id,
            mapping=bundle,
            excluded_record_types=excluded_rt,
        )
        log.kv(rows=len(opportunities),
               won=sum(1 for o in opportunities if o.get(bundle.is_won_field)),
               lost=sum(1 for o in opportunities if not o.get(bundle.is_won_field)))
        _enforce_minimum(opportunities, bundle)

        activities = await fetch_activities_for_opportunities(
            tenant_id=tenant_id,
            opportunity_ids=[o["Id"] for o in opportunities if o.get("Id")],
        )
        total_acts = sum(len(v) for v in activities.values())
        log.info(f"activities fetched: {total_acts} rows across {len(activities)} opps")

        df = build_feature_frame(opportunities, activities, bundle)
        y = targets_from_records(opportunities, bundle)

        custom_categorical = [
            cf.get("feature_name") for cf in bundle.custom_fields
            if cf.get("feature_name") and cf.get("type") == "categorical"
        ]
        X = one_hot_and_align(
            df,
            categorical_cols=CATEGORICAL_BASE_COLS,
            custom_categorical_cols=custom_categorical,
        )
        log.kv(feature_columns=X.shape[1], samples=X.shape[0])

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y,
        )
        log.kv(train_rows=len(X_train), test_rows=len(X_test))

        model = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            min_data_in_leaf=5,
            objective="binary",
            # Auto-balance class weights for imbalanced datasets (e.g., 17% won / 83% lost
            # in production B2B sales data). Without this, the model can collapse to "predict
            # loss" because that's accurate by base rate. is_unbalance=True instructs LightGBM
            # to compute scale_pos_weight = neg_count / pos_count automatically.
            is_unbalance=True,
            random_state=42,
            verbose=-1,
        )
        # eval_set gives us per-iteration val loss for the log.
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            eval_metric="binary_logloss",
            callbacks=[
                lgb.log_evaluation(period=0),    # silence lgb's stdout
                _LogEveryNRounds(log, period=50),
            ],
        )
        log.info("boosting complete")

        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]
        metrics = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision_won": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall_won": float(recall_score(y_test, y_pred, zero_division=0)),
            "auc": float(roc_auc_score(y_test, y_proba)) if len(set(y_test)) > 1 else 0.0,
        }
        # Persist holdout predictions for the Accuracy endpoint. We store
        # (probability, actual, opp_id) per test row — enough to rebuild a
        # confusion matrix + accuracy-by-confidence-bucket view later without
        # re-running inference.
        holdout_predictions = [
            {
                "probability": float(y_proba[i]),
                "actual": int(y_test.iloc[i]) if hasattr(y_test, "iloc") else int(y_test[i]),
                "opp_id": str(X_test.index[i]) if hasattr(X_test, "index") else "",
            }
            for i in range(len(y_test))
        ]
        log.info("holdout eval")
        log.kv(accuracy=f"{metrics['accuracy']:.4f}",
               auc=f"{metrics['auc']:.4f}",
               precision=f"{metrics['precision_won']:.4f}",
               recall=f"{metrics['recall_won']:.4f}")

        importances_raw = np.asarray(model.feature_importances_, dtype=float)
        total_importance = float(importances_raw.sum()) or 1.0
        feature_importances = sorted(
            [
                {"feature": col, "importance": float(importances_raw[i]) / total_importance}
                for i, col in enumerate(X.columns)
            ],
            key=lambda d: d["importance"],
            reverse=True,
        )

        async with async_session() as db:
            next_version = await _next_version(db, tenant_id)
            path = _model_path(tenant_id, next_version)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump({
                    "model": model,
                    "feature_columns": list(X.columns),
                    "categorical_cols": CATEGORICAL_BASE_COLS,
                    "custom_categorical_cols": custom_categorical,
                    "trained_at": datetime.now(timezone.utc).isoformat(),
                }, f)
            pickle_size = os.path.getsize(path)
            log.kv(model_path=path, size_bytes=pickle_size)

            await db.execute(
                update(DealInsightModel)
                .where(DealInsightModel.tenant_id == tenant_id, DealInsightModel.is_active.is_(True))
                .values(is_active=False)
            )
            duration = time.perf_counter() - started
            closed_won = int(y.sum())
            closed_lost = int(len(y) - closed_won)

            quality_tier = classify_data_quality_tier(len(opportunities))
            row = DealInsightModel(
                tenant_id=tenant_id,
                version=next_version,
                model_path=path,
                training_rows=len(opportunities),
                closed_won_count=closed_won,
                closed_lost_count=closed_lost,
                accuracy=metrics["accuracy"],
                precision_won=metrics["precision_won"],
                recall_won=metrics["recall_won"],
                auc=metrics["auc"],
                trained_at=datetime.now(timezone.utc),
                training_duration_seconds=duration,
                is_active=True,
                data_quality_tier=quality_tier,
            )
            row.feature_names_list = list(X.columns)
            row.feature_importances_list = feature_importances
            row.holdout_predictions_list = holdout_predictions
            db.add(row)
            await db.commit()
            await db.refresh(row)
            log.kv(data_quality_tier=quality_tier)

        # Session 6.5 — refresh bootstrap cache so confidence ranges are
        # available on the very next prediction. Cheap for standard/mature
        # tiers (20 × n_estimators=50 trees on 5000 rows trains in ~2s).
        try:
            from app.services.insights.bootstrap import build_bootstrap_models
            n_boot = build_bootstrap_models(
                X_train, y_train,
                tenant_id=tenant_id,
                model_version=next_version,
                model_root=MODEL_STORAGE_ROOT,
            )
            log.kv(bootstrap_models=n_boot)
        except Exception as e:
            log.error(f"bootstrap build failed (non-fatal): {e}")

        log.kv(version=next_version, duration_s=f"{duration:.2f}")
        log.info("training finished cleanly")

    logger.info(
        "insights.train tenant=%s version=%d rows=%d auc=%.3f acc=%.3f duration=%.1fs",
        tenant_id, next_version, len(opportunities), metrics["auc"],
        metrics["accuracy"], duration,
    )
    return row


class _LogEveryNRounds:
    """LightGBM callback that writes eval-metric snapshots to our training log
    every N boosting rounds. Using a lightweight class so it's picklable-safe
    if training ever moves to a subprocess."""

    def __init__(self, log, *, period: int = 50) -> None:
        self._log = log
        self._period = period

    def __call__(self, env) -> None:
        if env.iteration == 0 or (env.iteration + 1) % self._period != 0:
            return
        parts = [f"boost {env.iteration + 1}"]
        for data_name, metric_name, value, *_ in env.evaluation_result_list:
            parts.append(f"{data_name}.{metric_name}={value:.4f}")
        self._log.info("  " + "  ".join(parts))


async def train_in_background(tenant_id: str, job: TrainingJobStatus) -> None:
    """Wrapper used by the router — catches errors and records them on the job."""
    try:
        job.message = "loading mapping + pulling Salesforce data"
        model_row = await train_model_for_tenant(tenant_id)
        job.state = "done"
        job.finished_at = datetime.now(timezone.utc)
        job.message = f"trained v{model_row.version}"
        job.metrics = {
            "version": model_row.version,
            "training_rows": model_row.training_rows,
            "accuracy": model_row.accuracy,
            "precision_won": model_row.precision_won,
            "recall_won": model_row.recall_won,
            "auc": model_row.auc,
            "trained_at": model_row.trained_at.isoformat() if model_row.trained_at else None,
        }
    except InsightsTrainingError as e:
        job.state = "error"
        job.finished_at = datetime.now(timezone.utc)
        job.error_code = e.code
        job.message = str(e)
    except Exception as e:
        logger.exception("unexpected training failure tenant=%s: %s", tenant_id, e)
        job.state = "error"
        job.finished_at = datetime.now(timezone.utc)
        job.error_code = "internal_error"
        job.message = f"internal error: {e}"


# ─── Helpers ───────────────────────────────────────────────────────

async def _load_mapping(db: AsyncSession, tenant_id: str) -> DealInsightMapping | None:
    res = await db.execute(
        select(DealInsightMapping).where(DealInsightMapping.tenant_id == tenant_id)
    )
    return res.scalar_one_or_none()


def _mapping_to_bundle(row: DealInsightMapping) -> MappingBundle:
    return MappingBundle(
        amount_field=row.amount_field,
        stage_field=row.stage_field,
        close_date_field=row.close_date_field,
        created_date_field=row.created_date_field,
        is_closed_field=row.is_closed_field,
        is_won_field=row.is_won_field,
        industry_field=row.industry_field,
        lead_source_field=row.lead_source_field,
        owner_field=row.owner_field,
        record_type_field=row.record_type_field,
        custom_fields=row.custom_fields_list,
        product_tier_field=getattr(row, "product_tier_field", None),
        billing_country_field=getattr(row, "billing_country_field", None)
            or "Account.BillingCountry",
        stage_change_date_field=getattr(row, "stage_change_date_field", None),
    )


def _enforce_minimum(
    opportunities: list[dict[str, Any]],
    mapping: MappingBundle,
) -> None:
    n = len(opportunities)
    if n < MIN_DEALS_HARD_FLOOR:
        raise InsufficientDataError(
            f"Your org has {n} closed Opportunities. QuoteForge needs at least "
            f"{MIN_DEALS_HARD_FLOOR} to train a reliable model. We'll enable "
            f"predictions once you reach that threshold."
        )
    won = sum(1 for o in opportunities if bool(o.get(mapping.is_won_field)))
    lost = n - won
    if won == 0 or lost == 0:
        raise UnsupportedDataError(
            "Your closed deals are all one outcome — the model needs both wins "
            "and losses to learn from. Close deals from both sides and retry."
        )
    if won < MIN_WINS or lost < MIN_LOSSES:
        raise InsufficientDataError(
            f"Class imbalance too extreme: {won} won / {lost} lost. Each side "
            f"needs at least {MIN_WINS}. Close more deals across both outcomes."
        )


async def _next_version(db: AsyncSession, tenant_id: str) -> int:
    res = await db.execute(
        select(DealInsightModel.version)
        .where(DealInsightModel.tenant_id == tenant_id)
        .order_by(DealInsightModel.version.desc())
    )
    rows = res.scalars().all()
    return (rows[0] + 1) if rows else 1


def _model_path(tenant_id: str, version: int) -> str:
    return os.path.join(MODEL_STORAGE_ROOT, tenant_id, f"v{version}.pkl")
