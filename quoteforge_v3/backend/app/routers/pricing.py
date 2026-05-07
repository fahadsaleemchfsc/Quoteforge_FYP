from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.pricing_rule import PricingRule
from app.schemas.pricing import PricingRuleCreate, PricingRuleUpdate

router = APIRouter(prefix="/pricing", tags=["pricing"])


def _serialize(r: PricingRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "type": r.type,
        "condition": r.condition,
        "value": r.value,
        "region": r.region,
        "status": r.status,
    }


@router.get("/rules")
async def list_rules(
    type: str = Query("", alias="type"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(PricingRule)
    if type and type.lower() not in ("", "all"):
        query = query.where(PricingRule.type == type)
    result = await db.execute(query.order_by(PricingRule.id))
    return [_serialize(r) for r in result.scalars().all()]


@router.post("/rules")
async def create_rule(data: PricingRuleCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    rule = PricingRule(**data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _serialize(rule)


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, data: PricingRuleUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(PricingRule).where(PricingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    return _serialize(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(PricingRule).where(PricingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"message": "Rule deleted"}


@router.get("/compliance")
async def get_compliance(_=Depends(get_current_user)):
    return {
        "frameworks": [
            {
                "name": "SOC 2",
                "description": "Service Organization Control 2 — Security, Availability, Processing Integrity, Confidentiality, Privacy",
                "status": "active",
                "checklist": [
                    {"item": "Data encryption at rest and in transit", "checked": True},
                    {"item": "Access control and authentication", "checked": True},
                    {"item": "Audit logging enabled", "checked": True},
                    {"item": "Incident response plan documented", "checked": True},
                ],
            },
            {
                "name": "GDPR",
                "description": "General Data Protection Regulation — EU data protection and privacy",
                "status": "active",
                "checklist": [
                    {"item": "Data Processing Agreement (DPA)", "checked": True},
                    {"item": "Right to erasure supported", "checked": True},
                    {"item": "Data minimization enforced", "checked": True},
                    {"item": "Consent management implemented", "checked": False},
                ],
            },
            {
                "name": "PPRA",
                "description": "Public Procurement Regulatory Authority — Pakistan procurement transparency",
                "status": "active",
                "checklist": [
                    {"item": "Transparent pricing documentation", "checked": True},
                    {"item": "Competitive bidding support", "checked": True},
                    {"item": "Procurement workflow compliance", "checked": True},
                    {"item": "Audit trail for public sector", "checked": True},
                ],
            },
        ]
    }
