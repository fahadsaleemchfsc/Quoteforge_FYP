"""
Deal Insights router — Module 6 (win-probability predictor).

Endpoints (all under /api/insights, admin auth required):

  GET  /schema                  — inspect customer's SF Opportunity schema
  GET  /mapping                 — current saved mapping (or null if not yet)
  POST /mapping                 — save a mapping from the wizard
  POST /train                   — trigger background training, returns job_id
  GET  /status                  — latest job + active model metrics
  GET  /models                  — all model versions sorted newest-first
  GET  /predict/{opp_id}        — win probability + drivers + explanation
  POST /predict/batch           — predict up to N Opps in one request (demo-path)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id
from app.models.insights import (
    DealInsightMapping,
    DealInsightModel,
    DealInsightPrediction,
)
from app.services.insights.predictor import (
    PredictionError,
    generate_explanation_with_haiku,
    predict_for_opportunity,
)
from app.services.insights.schema_inspector import (
    inspect_salesforce_schema,
    suggest_mapping,
)
from app.services.insights.trainer import (
    InsightsTrainingError,
    TrainingJobStatus,
    get_job,
    get_latest_job_for_tenant,
    register_job,
    train_in_background,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


# ─── Schemas ───────────────────────────────────────────────────────

class FieldInfo(BaseModel):
    api_name: str
    label: str
    type: str


class RecordTypeInfo(BaseModel):
    id: str
    name: str


class SchemaInspectResponse(BaseModel):
    opportunity_fields: list[FieldInfo]
    custom_fields: list[FieldInfo]
    record_types: list[RecordTypeInfo]
    detected_activity_types: list[str]
    opportunity_count: int
    connected: bool


class CustomFieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sf_field: str = Field(min_length=1, max_length=255)
    feature_name: str = Field(min_length=1, max_length=100)
    type: str = Field(pattern="^(numeric|categorical|boolean)$")


class MappingPayload(BaseModel):
    """Fields the wizard submits. Mirrors the DealInsightMapping row."""
    model_config = ConfigDict(extra="forbid")

    amount_field: str = "Amount"
    stage_field: str = "StageName"
    close_date_field: str = "CloseDate"
    created_date_field: str = "CreatedDate"
    is_closed_field: str = "IsClosed"
    is_won_field: str = "IsWon"
    industry_field: str | None = "Account.Industry"
    lead_source_field: str | None = "LeadSource"
    owner_field: str | None = "OwnerId"
    record_type_field: str | None = "RecordTypeId"
    excluded_record_types: list[str] = Field(default_factory=list)
    custom_fields: list[CustomFieldSpec] = Field(default_factory=list)
    auto_suggested: bool = False


class MappingResponse(BaseModel):
    id: str
    tenant_id: str
    amount_field: str
    stage_field: str
    close_date_field: str
    created_date_field: str
    is_closed_field: str
    is_won_field: str
    industry_field: str | None
    lead_source_field: str | None
    owner_field: str | None
    record_type_field: str | None
    excluded_record_types: list[str]
    custom_fields: list[dict[str, Any]]
    auto_suggested: bool
    suggestions: list[dict[str, Any]] | None = None


class TrainingJobResponse(BaseModel):
    job_id: str
    state: str
    message: str


class TrainingStatusResponse(BaseModel):
    tenant_id: str
    latest_job: dict[str, Any] | None
    active_model: dict[str, Any] | None


class ModelSummary(BaseModel):
    id: str
    version: int
    training_rows: int
    closed_won_count: int
    closed_lost_count: int
    accuracy: float
    precision_won: float
    recall_won: float
    auc: float
    training_duration_seconds: float
    trained_at: str
    is_active: bool
    feature_names: list[str]
    feature_importances: list[dict[str, Any]]


class DriverInfo(BaseModel):
    feature: str
    shap_value: float
    direction: str  # "positive" | "negative"


class PredictionResponse(BaseModel):
    opportunity_id: str
    model_version: int
    win_probability: float
    probability_percent: int
    # Session 6.5 — bootstrap range. Absent on legacy predictions or when
    # the bootstrap cache isn't warm; UI falls back to a point estimate.
    probability_lower: float | None = None
    probability_upper: float | None = None
    band: str  # "high" | "medium" | "low"
    top_drivers: list[DriverInfo]
    explanation_text: str | None
    predicted_at: str
    # Phase 3 — ICP match (if an active ICP is configured for the tenant).
    # Absent/null when no ICP exists; the LWC renders only win probability.
    icp: dict[str, Any] | None = None


class BatchPredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opportunity_ids: list[str] = Field(min_length=1, max_length=100)


class BatchPredictResponse(BaseModel):
    results: list[dict[str, Any]]          # mix of success + {opportunity_id, error}
    success_count: int
    error_count: int


# ─── Schema + mapping endpoints ────────────────────────────────────

@router.get("/schema", response_model=SchemaInspectResponse)
async def get_schema(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    schema = await inspect_salesforce_schema(tenant_id, db)
    return SchemaInspectResponse(**schema)


@router.get("/mapping", response_model=MappingResponse | None)
async def get_mapping(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = await _load_mapping(db, tenant_id)
    if row is None:
        # Auto-suggest from schema when nothing saved yet. Wizard pre-fills from this.
        schema = await inspect_salesforce_schema(tenant_id, db)
        draft = suggest_mapping(schema).to_response()
        return MappingResponse(
            id="",
            tenant_id=tenant_id,
            amount_field=draft["amount_field"],
            stage_field=draft["stage_field"],
            close_date_field=draft["close_date_field"],
            created_date_field=draft["created_date_field"],
            is_closed_field=draft["is_closed_field"],
            is_won_field=draft["is_won_field"],
            industry_field=draft["industry_field"],
            lead_source_field=draft["lead_source_field"],
            owner_field=draft["owner_field"],
            record_type_field=draft["record_type_field"],
            excluded_record_types=draft["excluded_record_types"],
            custom_fields=draft["custom_fields"],
            auto_suggested=True,
            suggestions=draft["suggestions"],
        )
    return _serialize_mapping(row)


@router.post("/mapping", response_model=MappingResponse)
async def save_mapping(
    body: MappingPayload,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = await _load_mapping(db, tenant_id)
    if row is None:
        row = DealInsightMapping(tenant_id=tenant_id)
        db.add(row)

    row.amount_field = body.amount_field
    row.stage_field = body.stage_field
    row.close_date_field = body.close_date_field
    row.created_date_field = body.created_date_field
    row.is_closed_field = body.is_closed_field
    row.is_won_field = body.is_won_field
    row.industry_field = body.industry_field
    row.lead_source_field = body.lead_source_field
    row.owner_field = body.owner_field
    row.record_type_field = body.record_type_field
    row.excluded_record_types_list = body.excluded_record_types
    row.custom_fields_list = [cf.model_dump() for cf in body.custom_fields]
    row.auto_suggested = body.auto_suggested

    await db.commit()
    await db.refresh(row)
    return _serialize_mapping(row)


# ─── Training endpoints ────────────────────────────────────────────

@router.post("/train", response_model=TrainingJobResponse)
async def trigger_training(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    mapping = await _load_mapping(db, tenant_id)
    if mapping is None:
        raise HTTPException(
            400, "mapping missing — complete the Deal Insights setup wizard first.",
        )

    # Guard: if a job is already running for this tenant, reuse it.
    existing = get_latest_job_for_tenant(tenant_id)
    if existing and existing.state == "running":
        return TrainingJobResponse(
            job_id=existing.job_id, state=existing.state, message=existing.message,
        )

    job = register_job(tenant_id)
    asyncio.create_task(train_in_background(tenant_id, job))
    return TrainingJobResponse(
        job_id=job.job_id, state=job.state,
        message="training started in background",
    )


@router.get("/status", response_model=TrainingStatusResponse)
async def training_status(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    job = get_latest_job_for_tenant(tenant_id)
    latest_job: dict[str, Any] | None = None
    if job is not None:
        latest_job = {
            "job_id": job.job_id,
            "state": job.state,
            "message": job.message,
            "error_code": job.error_code,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "metrics": job.metrics,
        }

    active = await _load_active_model(db, tenant_id)
    active_model = _serialize_model(active) if active is not None else None

    return TrainingStatusResponse(
        tenant_id=tenant_id,
        latest_job=latest_job,
        active_model=active_model,
    )


@router.get("/training-log")
async def get_training_log(
    tail: int = 200,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Tail of the tenant's training_log.txt. Powers the Model Management
    LWC's on-page log streamer — polls this endpoint every 2s while a
    training job is in progress."""
    import os
    from app.services.insights.trainer import MODEL_STORAGE_ROOT
    log_path = os.path.join(MODEL_STORAGE_ROOT, tenant_id, "training_log.txt")
    if not os.path.exists(log_path):
        return {"tenant_id": tenant_id, "lines": [], "path": log_path}
    tail = max(1, min(2000, tail))
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return {
        "tenant_id": tenant_id,
        "lines": [ln.rstrip("\n") for ln in lines[-tail:]],
        "path": log_path,
        "total_lines": len(lines),
    }


@router.get("/models", response_model=list[ModelSummary])
async def list_models(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    res = await db.execute(
        select(DealInsightModel)
        .where(DealInsightModel.tenant_id == tenant_id)
        .order_by(DealInsightModel.version.desc())
    )
    return [ModelSummary(**_serialize_model(r)) for r in res.scalars().all()]


# ─── Accuracy (Session 6.5) ────────────────────────────────────────

@router.get("/accuracy")
async def get_model_accuracy(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Data for the Model Accuracy tab. Returns holdout metrics, confusion
    matrix, accuracy-by-confidence-bucket, recent-closed-deals check, and a
    retrain recommendation. Entirely offline — no inference runs, just
    reads the persisted holdout predictions from the active model row."""
    active = await _load_active_model(db, tenant_id)
    if active is None:
        raise HTTPException(409, "No active Deal Insights model. Train one first.")

    holdout = active.holdout_predictions_list or []
    # Confusion matrix (threshold 0.5 for predicted class).
    tp = fp = tn = fn = 0
    for h in holdout:
        predicted_win = h.get("probability", 0) >= 0.5
        actual_win = bool(h.get("actual"))
        if predicted_win and actual_win: tp += 1
        elif predicted_win and not actual_win: fp += 1
        elif not predicted_win and not actual_win: tn += 1
        else: fn += 1

    # Accuracy-by-confidence buckets.
    buckets = [(0.8, 1.01, "80-100%"), (0.6, 0.8, "60-80%"),
               (0.4, 0.6, "40-60%"), (0.2, 0.4, "20-40%"),
               (0.0, 0.2, "0-20%")]
    bucket_rows = []
    for lo, hi, label in buckets:
        subset = [h for h in holdout if lo <= h.get("probability", 0) < hi]
        won = sum(1 for h in subset if h.get("actual"))
        total = len(subset)
        bucket_rows.append({
            "bucket": label, "count": total,
            "actual_win_rate": round(won / total, 3) if total else 0.0,
        })

    # Recent closed deals — last 10 predictions the model has on file whose
    # Opp has since closed. We key off DealInsightPrediction rows that are
    # older than the closed-Opp window; in practice here we surface the
    # persisted holdout rows as the "recent closed" proxy.
    recent = []
    for h in sorted(holdout, key=lambda r: r.get("opp_id", ""), reverse=True)[:10]:
        recent.append({
            "sf_opportunity_id": h.get("opp_id", ""),
            "name": "",   # unknown without SF join
            "predicted_probability_at_close": round(h.get("probability", 0), 3),
            "actual_outcome": "won" if h.get("actual") else "lost",
            "close_date": active.trained_at.isoformat() if active.trained_at else None,
        })

    # Retrain recommendation — deals closed since trained_at. Synthetic tenants
    # don't have live SF deals, so we approximate: if >50 new predictions
    # exist against this model version, recommend retraining.
    new_preds = (await db.execute(
        select(DealInsightPrediction).where(
            DealInsightPrediction.tenant_id == tenant_id,
            DealInsightPrediction.model_version == active.version,
        )
    )).scalars().all()
    deals_since = len(new_preds)
    retrain_recommended = deals_since >= 50

    return {
        "tenant_id": tenant_id,
        "model_version": active.version,
        "data_quality_tier": active.data_quality_tier or "unknown",
        "training_row_count": active.training_rows,
        "holdout_row_count": len(holdout),
        "holdout_metrics": {
            "accuracy": active.accuracy,
            "precision": active.precision_won,
            "recall": active.recall_won,
            "auc": active.auc,
        },
        "confusion_matrix": {
            "true_positive": tp, "false_positive": fp,
            "true_negative": tn, "false_negative": fn,
        },
        "accuracy_by_confidence_bucket": bucket_rows,
        "recent_closed_deals": recent,
        "deals_since_last_training": deals_since,
        "retrain_recommended": retrain_recommended,
        "retrain_reason": (
            f"{deals_since} new predictions since last training"
            if retrain_recommended else None
        ),
    }


# ─── Prediction endpoints ──────────────────────────────────────────

@router.get("/predict/{opportunity_id}", response_model=PredictionResponse)
async def get_prediction(
    opportunity_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    try:
        prediction = await predict_for_opportunity(tenant_id, opportunity_id)
    except PredictionError as e:
        code = {"no_model": 409, "mapping_missing": 409,
                "opportunity_not_found": 404}.get(e.code, 400)
        raise HTTPException(code, str(e))
    return _serialize_prediction(prediction)


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch(
    body: BatchPredictRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Demo-path: sequential iteration with per-item error catch. Production
    would parallelize + add rate limiting. See Phase 2 in README."""
    results: list[dict[str, Any]] = []
    success = 0
    errors = 0
    for opp_id in body.opportunity_ids:
        try:
            pred = await predict_for_opportunity(tenant_id, opp_id)
            results.append(_serialize_prediction(pred).model_dump())
            success += 1
        except PredictionError as e:
            results.append({"opportunity_id": opp_id, "error": str(e), "error_code": e.code})
            errors += 1
        except Exception as e:
            logger.exception("insights.batch: unexpected error for %s", opp_id)
            results.append({"opportunity_id": opp_id, "error": str(e), "error_code": "internal_error"})
            errors += 1
    return BatchPredictResponse(results=results, success_count=success, error_count=errors)


# ─── Serialization helpers ─────────────────────────────────────────

async def _load_mapping(db: AsyncSession, tenant_id: str) -> DealInsightMapping | None:
    res = await db.execute(
        select(DealInsightMapping).where(DealInsightMapping.tenant_id == tenant_id)
    )
    return res.scalar_one_or_none()


async def _load_active_model(
    db: AsyncSession, tenant_id: str,
) -> DealInsightModel | None:
    res = await db.execute(
        select(DealInsightModel)
        .where(
            DealInsightModel.tenant_id == tenant_id,
            DealInsightModel.is_active.is_(True),
        )
        .order_by(DealInsightModel.version.desc())
    )
    return res.scalars().first()


def _serialize_mapping(row: DealInsightMapping) -> MappingResponse:
    return MappingResponse(
        id=row.id,
        tenant_id=row.tenant_id,
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
        excluded_record_types=row.excluded_record_types_list,
        custom_fields=row.custom_fields_list,
        auto_suggested=row.auto_suggested,
    )


def _serialize_model(row: DealInsightModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "version": row.version,
        "training_rows": row.training_rows,
        "closed_won_count": row.closed_won_count,
        "closed_lost_count": row.closed_lost_count,
        "accuracy": row.accuracy,
        "precision_won": row.precision_won,
        "recall_won": row.recall_won,
        "auc": row.auc,
        "training_duration_seconds": row.training_duration_seconds,
        "trained_at": row.trained_at.isoformat() if row.trained_at else "",
        "is_active": row.is_active,
        "feature_names": row.feature_names_list,
        "feature_importances": row.feature_importances_list,
    }


def _serialize_prediction(row: DealInsightPrediction) -> PredictionResponse:
    prob = row.win_probability
    pct = int(round(prob * 100))
    if prob >= 0.60:
        band = "high"
    elif prob >= 0.40:
        band = "medium"
    else:
        band = "low"
    # Phase 3 — _icp is stashed on the returned SQLAlchemy row by the
    # predictor when an active ICP exists. Transient attribute, not a DB col.
    icp = getattr(row, "__dict__", {}).get("_icp")
    return PredictionResponse(
        opportunity_id=row.sf_opportunity_id,
        model_version=row.model_version,
        win_probability=prob,
        probability_percent=pct,
        probability_lower=row.probability_lower,
        probability_upper=row.probability_upper,
        band=band,
        top_drivers=[DriverInfo(**d) for d in row.top_drivers_list],
        explanation_text=row.explanation_text,
        predicted_at=row.predicted_at.isoformat() if row.predicted_at else "",
        icp=icp,
    )
