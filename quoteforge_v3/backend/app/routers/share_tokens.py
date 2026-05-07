"""
Admin — create and list buyer-room share tokens.

  POST /api/share-tokens       — create, returns full share URL
  GET  /api/share-tokens       — list active tokens for current tenant
  DELETE /api/share-tokens/{id} — revoke (sets expires_at to now)
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_tenant_id, get_current_user
from app.models.deal_share_token import DealShareToken
from app.models.user import User
from app.schemas.share_token import ShareTokenCreate, ShareTokenList, ShareTokenOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/share-tokens", tags=["share-tokens"])


def _make_token() -> str:
    return secrets.token_urlsafe(24)     # ~32 URL-safe chars


def _to_out(row: DealShareToken) -> ShareTokenOut:
    base = settings.BUYER_ROOM_PUBLIC_BASE.rstrip("/")
    return ShareTokenOut(
        id=row.id,
        token=row.token,
        label=row.label,
        share_url=f"{base}/buy/{row.token}",
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
    )


@router.post("", response_model=ShareTokenOut)
async def create_share_token(
    payload: ShareTokenCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ShareTokenOut:
    now = datetime.now(timezone.utc)
    row = DealShareToken(
        token=_make_token(),
        seller_tenant_id=tenant_id,
        created_by_user_id=user.id,
        label=payload.label,
        expires_at=now + timedelta(days=payload.expires_in_days),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("share token created by=%s label=%s token=%s...", user.email, payload.label, row.token[:8])
    return _to_out(row)


@router.get("", response_model=ShareTokenList)
async def list_share_tokens(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ShareTokenList:
    rows = (await db.execute(
        select(DealShareToken)
        .where(DealShareToken.seller_tenant_id == tenant_id)
        .order_by(DealShareToken.created_at.desc())
    )).scalars().all()
    return ShareTokenList(tokens=[_to_out(r) for r in rows])


@router.delete("/{token_id}")
async def revoke_share_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict:
    row = (await db.execute(
        select(DealShareToken).where(
            DealShareToken.id == token_id,
            DealShareToken.seller_tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="token not found")
    row.expires_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("share token revoked by=%s token=%s...", user.email, row.token[:8])
    return {"status": "revoked"}
