"""
Tenant config admin endpoints.

GET  /api/tenant/config    — current negotiation policy
PUT  /api/tenant/config    — partial update (threshold and/or auto-commit)

Multi-tenant: the active tenant is derived from the authenticated user's
tenant_id (carried in the JWT). Each tenant sees only its own config.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id, get_current_user
from app.models.tenant_config import TenantConfig
from app.models.user import User
from app.schemas.tenant_config import TenantConfigOut, TenantConfigUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenant/config", tags=["tenant"])


async def _load_config(db: AsyncSession, tenant_id: str) -> TenantConfig:
    cfg = (
        await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
    ).scalar_one()
    return cfg


def _to_out(cfg: TenantConfig) -> TenantConfigOut:
    mode = cfg.negotiation_mode or "deterministic"
    if mode not in ("ai_first", "deterministic"):
        mode = "deterministic"
    return TenantConfigOut(
        tenant_id=cfg.tenant_id,
        approval_threshold_cents=int(cfg.approval_threshold_cents),
        auto_commit_enabled=bool(cfg.auto_commit_enabled),
        negotiation_mode=mode,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


@router.get("", response_model=TenantConfigOut)
async def get_config(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> TenantConfigOut:
    cfg = await _load_config(db, tenant_id)
    return _to_out(cfg)


@router.put("", response_model=TenantConfigOut)
async def update_config(
    payload: TenantConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> TenantConfigOut:
    cfg = await _load_config(db, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    logger.info(
        "tenant config updated tenant=%s by=%s fields=%s",
        cfg.tenant_id, user.email, list(updates),
    )
    return _to_out(cfg)
