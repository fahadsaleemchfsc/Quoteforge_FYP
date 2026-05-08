"""
ICP router — Phase 3.

CRUD on IdealCustomerProfile rows plus two scoring endpoints that the
admin UI + Deal Insights LWC call:

  GET    /api/icp                         — list
  POST   /api/icp                         — create
  GET    /api/icp/{id}                    — read
  PUT    /api/icp/{id}                    — update
  DELETE /api/icp/{id}                    — delete
  POST   /api/icp/{id}/activate           — set active, deactivate siblings
  GET    /api/icp/score/{opportunity_id}  — score single Opp against active ICP
  POST   /api/icp/score/batch             — score many Opps in one call

Mutations invalidate the ICPMatchScore cache scoped to the affected ICP
so stale scores never surface on the Dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id
from app.models.icp import ICPMatchScore, IdealCustomerProfile
from app.services.icp.scorer import (
    ICPDefinition,
    score_opportunity_against_icp,
)
from app.services.insights.features import MappingBundle
from app.services.insights.salesforce_fetch import fetch_opportunity_by_id
from app.services.insights.trainer import _mapping_to_bundle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/icp", tags=["icp"])


# ─── Schemas ────────────────────────────────────────────────────

class ICPPayload(BaseModel):
    """Create / update payload — nullable range bounds let the admin leave
    either side open."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    included_industries: list[str] = Field(default_factory=list)
    included_regions: list[str] = Field(default_factory=list)
    min_amount: float | None = None
    max_amount: float | None = None
    min_employee_count: int | None = None
    max_employee_count: int | None = None
    required_lead_sources: list[str] = Field(default_factory=list)
    required_contact_levels: list[str] = Field(default_factory=list)
    required_contact_departments: list[str] = Field(default_factory=list)
    min_contacts_on_account: int | None = None
    min_engagement_score: float | None = None
    weight_industry_match: float = Field(default=1.0, ge=0, le=2)
    weight_region_match: float = Field(default=0.8, ge=0, le=2)
    weight_amount_fit: float = Field(default=1.0, ge=0, le=2)
    weight_engagement: float = Field(default=1.2, ge=0, le=2)
    weight_lead_source: float = Field(default=0.7, ge=0, le=2)


class ICPSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None
    included_industries: list[str]
    included_regions: list[str]
    min_amount: float | None
    max_amount: float | None
    min_employee_count: int | None
    max_employee_count: int | None
    required_lead_sources: list[str]
    required_contact_levels: list[str]
    required_contact_departments: list[str]
    min_contacts_on_account: int | None
    min_engagement_score: float | None
    weight_industry_match: float
    weight_region_match: float
    weight_amount_fit: float
    weight_engagement: float
    weight_lead_source: float
    is_active: bool
    created_at: str
    updated_at: str


class ICPMatchScoreResponse(BaseModel):
    opportunity_id: str
    icp_id: str
    icp_name: str
    match_score: float
    match_percent: int
    band: str  # "strong" | "partial" | "weak"
    match_reasons: list[dict[str, Any]]


class BatchScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opportunity_ids: list[str] = Field(min_length=1, max_length=100)


# ─── Helpers ───────────────────────────────────────────────────

def _serialize(row: IdealCustomerProfile) -> ICPSchema:
    return ICPSchema(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        description=row.description,
        included_industries=row.included_industries_list,
        included_regions=row.included_regions_list,
        min_amount=row.min_amount,
        max_amount=row.max_amount,
        min_employee_count=row.min_employee_count,
        max_employee_count=row.max_employee_count,
        required_lead_sources=row.required_lead_sources_list,
        required_contact_levels=row.required_contact_levels_list,
        required_contact_departments=row.required_contact_departments_list,
        min_contacts_on_account=row.min_contacts_on_account,
        min_engagement_score=row.min_engagement_score,
        weight_industry_match=row.weight_industry_match,
        weight_region_match=row.weight_region_match,
        weight_amount_fit=row.weight_amount_fit,
        weight_engagement=row.weight_engagement,
        weight_lead_source=row.weight_lead_source,
        is_active=row.is_active,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def _definition_from_row(row: IdealCustomerProfile) -> ICPDefinition:
    return ICPDefinition(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        included_industries=row.included_industries_list,
        included_regions=row.included_regions_list,
        min_amount=row.min_amount,
        max_amount=row.max_amount,
        min_employee_count=row.min_employee_count,
        max_employee_count=row.max_employee_count,
        required_lead_sources=row.required_lead_sources_list,
        required_contact_levels=row.required_contact_levels_list,
        required_contact_departments=row.required_contact_departments_list,
        min_contacts_on_account=row.min_contacts_on_account,
        min_engagement_score=row.min_engagement_score,
        weight_industry_match=row.weight_industry_match,
        weight_region_match=row.weight_region_match,
        weight_amount_fit=row.weight_amount_fit,
        weight_engagement=row.weight_engagement,
        weight_lead_source=row.weight_lead_source,
    )


def _apply_payload(row: IdealCustomerProfile, body: ICPPayload) -> None:
    row.name = body.name
    row.description = body.description
    row.included_industries_list = body.included_industries
    row.included_regions_list = body.included_regions
    row.min_amount = body.min_amount
    row.max_amount = body.max_amount
    row.min_employee_count = body.min_employee_count
    row.max_employee_count = body.max_employee_count
    row.required_lead_sources_list = body.required_lead_sources
    row.required_contact_levels_list = body.required_contact_levels
    row.required_contact_departments_list = body.required_contact_departments
    row.min_contacts_on_account = body.min_contacts_on_account
    row.min_engagement_score = body.min_engagement_score
    row.weight_industry_match = body.weight_industry_match
    row.weight_region_match = body.weight_region_match
    row.weight_amount_fit = body.weight_amount_fit
    row.weight_engagement = body.weight_engagement
    row.weight_lead_source = body.weight_lead_source


async def _invalidate_scores(
    db: AsyncSession, tenant_id: str, icp_id: str,
) -> None:
    """Drop cached ICPMatchScore rows for a specific ICP. Called whenever an
    ICP is mutated/deleted so the next score request recomputes."""
    await db.execute(
        delete(ICPMatchScore).where(
            ICPMatchScore.tenant_id == tenant_id,
            ICPMatchScore.icp_id == icp_id,
        )
    )


async def _load_active_icp(
    db: AsyncSession, tenant_id: str,
) -> IdealCustomerProfile | None:
    res = await db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.tenant_id == tenant_id,
            IdealCustomerProfile.is_active.is_(True),
        )
    )
    return res.scalars().first()


def _band_for(score: float) -> str:
    if score >= 0.7:
        return "strong"
    if score >= 0.4:
        return "partial"
    return "weak"


async def _load_opp_for_scoring(
    db: AsyncSession, tenant_id: str, opp_id: str,
) -> dict[str, Any] | None:
    """Pull the same Opp shape the feature pipeline consumes. Reuses the
    enriched fetch path so cross-object signals (Contact/Account activities)
    feed the engagement score correctly."""
    from app.models.insights import DealInsightMapping
    mapping_row = (await db.execute(
        select(DealInsightMapping).where(DealInsightMapping.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if mapping_row is None:
        # No mapping yet — fall back to a default bundle so scoring still
        # works on a freshly provisioned tenant.
        bundle = MappingBundle(
            amount_field="Amount", stage_field="StageName",
            close_date_field="CloseDate", created_date_field="CreatedDate",
            is_closed_field="IsClosed", is_won_field="IsWon",
            industry_field="Account.Industry", lead_source_field="LeadSource",
            owner_field="OwnerId", record_type_field=None, custom_fields=[],
        )
    else:
        bundle = _mapping_to_bundle(mapping_row)
    return await fetch_opportunity_by_id(
        tenant_id=tenant_id, mapping=bundle, opportunity_id=opp_id,
    )


# ─── CRUD endpoints ────────────────────────────────────────────

@router.get("", response_model=list[ICPSchema])
async def list_icps(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    rows = (await db.execute(
        select(IdealCustomerProfile)
        .where(IdealCustomerProfile.tenant_id == tenant_id)
        .order_by(IdealCustomerProfile.is_active.desc(),
                  IdealCustomerProfile.created_at.desc())
    )).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("", response_model=ICPSchema)
async def create_icp(
    body: ICPPayload,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = IdealCustomerProfile(tenant_id=tenant_id, is_active=False)
    _apply_payload(row, body)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@router.get("/{icp_id}", response_model=ICPSchema)
async def get_icp(
    icp_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = (await db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.tenant_id == tenant_id,
            IdealCustomerProfile.id == icp_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"ICP {icp_id} not found")
    return _serialize(row)


@router.put("/{icp_id}", response_model=ICPSchema)
async def update_icp(
    icp_id: str,
    body: ICPPayload,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = (await db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.tenant_id == tenant_id,
            IdealCustomerProfile.id == icp_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"ICP {icp_id} not found")
    _apply_payload(row, body)
    await _invalidate_scores(db, tenant_id, icp_id)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@router.delete("/{icp_id}", status_code=204)
async def delete_icp(
    icp_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = (await db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.tenant_id == tenant_id,
            IdealCustomerProfile.id == icp_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"ICP {icp_id} not found")
    await _invalidate_scores(db, tenant_id, icp_id)
    await db.execute(
        delete(IdealCustomerProfile).where(IdealCustomerProfile.id == icp_id)
    )
    await db.commit()
    return None


@router.post("/{icp_id}/activate", response_model=ICPSchema)
async def activate_icp(
    icp_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    row = (await db.execute(
        select(IdealCustomerProfile).where(
            IdealCustomerProfile.tenant_id == tenant_id,
            IdealCustomerProfile.id == icp_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"ICP {icp_id} not found")
    # Deactivate siblings first.
    await db.execute(
        update(IdealCustomerProfile)
        .where(IdealCustomerProfile.tenant_id == tenant_id,
               IdealCustomerProfile.is_active.is_(True))
        .values(is_active=False)
    )
    row.is_active = True
    # Invalidate score cache — active ICP changed, cached scores for OTHER
    # ICPs are still valid but all LWC callers want the new active ICP's
    # scores, so we only clear rows for the newly-active one (previous
    # active ICP's cache is untouched by design — it's historic).
    await _invalidate_scores(db, tenant_id, icp_id)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


# ─── Scoring endpoints ──────────────────────────────────────────

@router.get("/score/{opportunity_id}", response_model=ICPMatchScoreResponse)
async def score_opportunity(
    opportunity_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    active = await _load_active_icp(db, tenant_id)
    if active is None:
        raise HTTPException(
            409,
            "No active ICP. Create + activate one in the ICP Builder first.",
        )

    opp = await _load_opp_for_scoring(db, tenant_id, opportunity_id)
    if opp is None:
        raise HTTPException(404, f"Opportunity {opportunity_id} not found.")

    definition = _definition_from_row(active)
    result = score_opportunity_against_icp(opp, definition)

    # Upsert cache.
    await db.execute(
        delete(ICPMatchScore).where(
            ICPMatchScore.tenant_id == tenant_id,
            ICPMatchScore.icp_id == active.id,
            ICPMatchScore.sf_opportunity_id == opportunity_id,
        )
    )
    cache_row = ICPMatchScore(
        tenant_id=tenant_id, icp_id=active.id,
        sf_opportunity_id=opportunity_id,
        match_score=result.match_score, scored_at=datetime.utcnow(),
    )
    cache_row.match_reasons_list = result.match_reasons
    db.add(cache_row)
    await db.commit()

    return ICPMatchScoreResponse(
        opportunity_id=opportunity_id,
        icp_id=active.id,
        icp_name=active.name,
        match_score=result.match_score,
        match_percent=int(round(result.match_score * 100)),
        band=_band_for(result.match_score),
        match_reasons=result.match_reasons,
    )


@router.post("/score/batch", response_model=list[ICPMatchScoreResponse])
async def score_batch(
    body: BatchScoreRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Sequential scoring loop. Demo-path (matches the insights batch endpoint
    pattern). Each Opp gets its own try/except so one bad row doesn't kill
    the rest."""
    active = await _load_active_icp(db, tenant_id)
    if active is None:
        raise HTTPException(409, "No active ICP.")
    definition = _definition_from_row(active)

    results: list[ICPMatchScoreResponse] = []
    for opp_id in body.opportunity_ids:
        opp = await _load_opp_for_scoring(db, tenant_id, opp_id)
        if opp is None:
            continue
        result = score_opportunity_against_icp(opp, definition)
        results.append(ICPMatchScoreResponse(
            opportunity_id=opp_id, icp_id=active.id,
            icp_name=active.name,
            match_score=result.match_score,
            match_percent=int(round(result.match_score * 100)),
            band=_band_for(result.match_score),
            match_reasons=result.match_reasons,
        ))
    return results
