"""
Ideal Customer Profile (ICP) — Module 6 / Phase 3.

Two tables:

  ideal_customer_profiles  — per-tenant ICP definitions (hard filters + soft
                             signals + weights). At most one is_active per
                             tenant at a time for v1.

  icp_match_scores         — cached scoring output per (tenant, icp, opp).
                             Scoring is deterministic so caches are cheap
                             to invalidate when the ICP definition mutates.

JSON-shaped fields are stored as Text (SQLite-friendly). Accessor properties
serialize on the way out + on the way in.
"""
from __future__ import annotations

import json
import uuid
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


class IdealCustomerProfile(Base):
    """Per-tenant ideal customer profile.

    Hard filters (industry/region/amount/employee range) cap the match score
    at 0 when violated — they're *exclusions*, not soft downweights. Soft
    signals (engagement score, lead source) contribute to a weighted sum
    scaled into [0, 1].
    """

    __tablename__ = "ideal_customer_profiles"
    __table_args__ = (
        Index("ix_icp_tenant_active", "tenant_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Hard inclusion filters — empty list = "all allowed".
    included_industries = Column(Text, nullable=False, default="[]")
    included_regions = Column(Text, nullable=False, default="[]")
    min_amount = Column(Float, nullable=True)
    max_amount = Column(Float, nullable=True)
    min_employee_count = Column(Integer, nullable=True)
    max_employee_count = Column(Integer, nullable=True)

    # Contact-level hard filters — empty list / NULL = "no filter".
    # required_contact_levels: subset of {C-level, VP, Director, Manager, IC};
    #   matched against the primary Contact's Title via a case-insensitive
    #   substring map (see scorer.LEVEL_PATTERNS).
    # required_contact_departments: matched against Contact.Department
    #   (case-insensitive substring).
    # min_contacts_on_account: requires at least N Contact records on the Opp's
    #   Account (uses _contact_count_on_account already populated at predict
    #   time by salesforce_fetch._enrich_opp_with_relations).
    required_contact_levels = Column(Text, nullable=False, default="[]")
    required_contact_departments = Column(Text, nullable=False, default="[]")
    min_contacts_on_account = Column(Integer, nullable=True)

    # Required signals (soft, but gated by a minimum threshold).
    required_lead_sources = Column(Text, nullable=False, default="[]")
    min_engagement_score = Column(Float, nullable=True)

    # Scoring weights — default shape biases toward engagement + industry
    # because those are the strongest signals from real sales data. All
    # weights are in [0, 2] — the UI slider caps match.
    weight_industry_match = Column(Float, nullable=False, default=1.0)
    weight_region_match = Column(Float, nullable=False, default=0.8)
    weight_amount_fit = Column(Float, nullable=False, default=1.0)
    weight_engagement = Column(Float, nullable=False, default=1.2)
    weight_lead_source = Column(Float, nullable=False, default=0.7)

    is_active = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ─── JSON accessors ──────────────────────────────────────────

    @property
    def included_industries_list(self) -> list[str]:
        return json.loads(self.included_industries or "[]")

    @included_industries_list.setter
    def included_industries_list(self, v: list[str]) -> None:
        self.included_industries = json.dumps(v or [])

    @property
    def included_regions_list(self) -> list[str]:
        return json.loads(self.included_regions or "[]")

    @included_regions_list.setter
    def included_regions_list(self, v: list[str]) -> None:
        self.included_regions = json.dumps(v or [])

    @property
    def required_lead_sources_list(self) -> list[str]:
        return json.loads(self.required_lead_sources or "[]")

    @required_lead_sources_list.setter
    def required_lead_sources_list(self, v: list[str]) -> None:
        self.required_lead_sources = json.dumps(v or [])

    @property
    def required_contact_levels_list(self) -> list[str]:
        return json.loads(self.required_contact_levels or "[]")

    @required_contact_levels_list.setter
    def required_contact_levels_list(self, v: list[str]) -> None:
        self.required_contact_levels = json.dumps(v or [])

    @property
    def required_contact_departments_list(self) -> list[str]:
        return json.loads(self.required_contact_departments or "[]")

    @required_contact_departments_list.setter
    def required_contact_departments_list(self, v: list[str]) -> None:
        self.required_contact_departments = json.dumps(v or [])


class ICPMatchScore(Base):
    """Cached scoring output for (tenant, ICP, Opportunity).

    Deleted when the underlying ICP mutates — the admin endpoints clear
    affected rows on update/activate/delete, so the predictor / Dashboard
    view never sees stale scores.
    """

    __tablename__ = "icp_match_scores"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "icp_id", "sf_opportunity_id",
            name="uq_icp_match_score",
        ),
        Index("ix_icp_scores_tenant_opp", "tenant_id", "sf_opportunity_id"),
    )

    id = Column(String(36), primary_key=True, default=_new_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    icp_id = Column(String(36), ForeignKey("ideal_customer_profiles.id"), nullable=False)

    sf_opportunity_id = Column(String(32), nullable=False)
    match_score = Column(Float, nullable=False)

    # JSON: list[{"factor": str, "status": "match|mismatch|partial", "detail": str}]
    match_reasons = Column(Text, nullable=False, default="[]")

    scored_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def match_reasons_list(self) -> list[dict[str, Any]]:
        return json.loads(self.match_reasons or "[]")

    @match_reasons_list.setter
    def match_reasons_list(self, v: list[dict[str, Any]]) -> None:
        self.match_reasons = json.dumps(v or [])
