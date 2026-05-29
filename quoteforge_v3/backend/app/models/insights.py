"""
Deal Insights (Module 6) — per-tenant win-probability predictor.

Three tables:

  deal_insight_mappings     — what SF fields to pull for this tenant
  deal_insight_models       — metadata for each trained LightGBM model
  deal_insight_predictions  — cached per-Opportunity win probabilities

JSON fields are stored as Text for SQLite compatibility (matches the existing
guardrail / replay event pattern). Helper properties serialize on read.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ─── Mapping ──────────────────────────────────────────────────────

class DealInsightMapping(Base):
    """Per-tenant field mapping the admin confirms at setup time.

    One row per tenant. The Mapping Wizard writes this; the trainer and
    predictor read it to know which SF fields to pull and which custom fields
    to feature-engineer.
    """

    __tablename__ = "deal_insight_mappings"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), unique=True, nullable=False)

    # Core required fields — defaults match stock SF Opportunity schema.
    amount_field = Column(String(255), nullable=False, default="Amount")
    stage_field = Column(String(255), nullable=False, default="StageName")
    close_date_field = Column(String(255), nullable=False, default="CloseDate")
    created_date_field = Column(String(255), nullable=False, default="CreatedDate")
    is_closed_field = Column(String(255), nullable=False, default="IsClosed")
    is_won_field = Column(String(255), nullable=False, default="IsWon")

    # Optional feature inputs (nullable — tenant may not use them).
    industry_field = Column(String(255), nullable=True, default="Account.Industry")
    lead_source_field = Column(String(255), nullable=True, default="LeadSource")
    owner_field = Column(String(255), nullable=True, default="OwnerId")
    record_type_field = Column(String(255), nullable=True, default="RecordTypeId")
    # Phase 2 — weak-signal + stage-history optional mappings.
    product_tier_field = Column(String(255), nullable=True)
    billing_country_field = Column(String(255), nullable=True,
                                   default="Account.BillingCountry")
    stage_change_date_field = Column(String(255), nullable=True)

    # JSON-serialized arrays. SQLite-compatible via Text.
    # excluded_record_types: list[str] — record-type IDs to filter out of training.
    # custom_fields: list[dict] — each dict is {sf_field, feature_name, type}.
    excluded_record_types = Column(Text, nullable=False, default="[]")
    custom_fields = Column(Text, nullable=False, default="[]")

    auto_suggested = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ─── Accessors ────────────────────────────────────
    @property
    def excluded_record_types_list(self) -> list[str]:
        return json.loads(self.excluded_record_types or "[]")

    @excluded_record_types_list.setter
    def excluded_record_types_list(self, v: list[str]) -> None:
        self.excluded_record_types = json.dumps(v or [])

    @property
    def custom_fields_list(self) -> list[dict[str, Any]]:
        return json.loads(self.custom_fields or "[]")

    @custom_fields_list.setter
    def custom_fields_list(self, v: list[dict[str, Any]]) -> None:
        self.custom_fields = json.dumps(v or [])


# ─── Models ──────────────────────────────────────────────────────

class DealInsightModel(Base):
    """Metadata for a trained LightGBM model.

    The pickle file itself lives on disk (see model_path). Rows here are
    append-only: each retrain creates a new version, deactivates the previous
    active model, and flips is_active=True on the new one. A single tenant
    can have at most one is_active=True row at a time (enforced by code, not
    a partial index, since SQLite support is inconsistent).
    """

    __tablename__ = "deal_insight_models"
    __table_args__ = (
        Index("ix_deal_insight_models_tenant_active", "tenant_id", "is_active"),
        UniqueConstraint("tenant_id", "version", name="uq_deal_insight_model_version"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)

    version = Column(Integer, nullable=False)
    model_path = Column(String(500), nullable=False)

    # Counts
    training_rows = Column(Integer, nullable=False, default=0)
    closed_won_count = Column(Integer, nullable=False, default=0)
    closed_lost_count = Column(Integer, nullable=False, default=0)

    # Metrics
    accuracy = Column(Float, nullable=False, default=0.0)
    precision_won = Column(Float, nullable=False, default=0.0)
    recall_won = Column(Float, nullable=False, default=0.0)
    auc = Column(Float, nullable=False, default=0.0)

    # JSON
    # feature_names: list[str]
    # feature_importances: list[{"feature": str, "importance": float}]
    feature_names = Column(Text, nullable=False, default="[]")
    feature_importances = Column(Text, nullable=False, default="[]")

    trained_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    training_duration_seconds = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, nullable=False, default=False)

    # Session 6.5 — data-quality classification (insufficient | early_stage |
    # standard | mature), used by the UI to set expectations about model
    # reliability. Nullable on legacy rows trained before this migration.
    data_quality_tier = Column(String(20), nullable=True)

    # JSON array of {probability, actual, opp_id} rows captured from the
    # holdout set at training time. Powers the Model Accuracy endpoint's
    # confusion matrix + accuracy-by-confidence-bucket breakdowns without
    # re-running inference at query time.
    holdout_predictions = Column(Text, nullable=True)

    # ─── Accessors ────────────────────────────────────
    @property
    def holdout_predictions_list(self) -> list[dict[str, Any]]:
        return json.loads(self.holdout_predictions or "[]")

    @holdout_predictions_list.setter
    def holdout_predictions_list(self, v: list[dict[str, Any]]) -> None:
        self.holdout_predictions = json.dumps(v or [])

    @property
    def feature_names_list(self) -> list[str]:
        return json.loads(self.feature_names or "[]")

    @feature_names_list.setter
    def feature_names_list(self, v: list[str]) -> None:
        self.feature_names = json.dumps(v or [])

    @property
    def feature_importances_list(self) -> list[dict[str, Any]]:
        return json.loads(self.feature_importances or "[]")

    @feature_importances_list.setter
    def feature_importances_list(self, v: list[dict[str, Any]]) -> None:
        self.feature_importances = json.dumps(v or [])


# ─── Predictions ──────────────────────────────────────────────────

class DealInsightPrediction(Base):
    """Cached predictions per open Opportunity.

    Invalidated when a new model version goes active — the worker deletes
    rows with stale model_version, forcing the next /predict call to
    re-run inference against the new model.
    """

    __tablename__ = "deal_insight_predictions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "sf_opportunity_id", "model_version",
            name="uq_deal_insight_prediction",
        ),
        Index("ix_deal_insight_predictions_tenant_opp", "tenant_id", "sf_opportunity_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    model_version = Column(Integer, nullable=False)

    sf_opportunity_id = Column(String(32), nullable=False)
    win_probability = Column(Float, nullable=False)

    # Session 6.5 — confidence-range endpoints from the bootstrap predictor.
    # Null on legacy rows; populated for new predictions when bootstrap
    # models are available for the tenant.
    probability_lower = Column(Float, nullable=True)
    probability_upper = Column(Float, nullable=True)

    # JSON: list[{"feature": str, "shap_value": float, "direction": "positive|negative"}]
    top_drivers = Column(Text, nullable=False, default="[]")

    # Haiku-generated; nullable because the explanation is computed lazily in a
    # background task after predict() returns.
    explanation_text = Column(Text, nullable=True)

    predicted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def top_drivers_list(self) -> list[dict[str, Any]]:
        return json.loads(self.top_drivers or "[]")

    @top_drivers_list.setter
    def top_drivers_list(self, v: list[dict[str, Any]]) -> None:
        self.top_drivers = json.dumps(v or [])
