"""
Public buyer-room router. No admin auth — share token is the cap.

  GET  /api/buyer-room/{token}/context     — validate token, return catalog + session_id
  POST /api/buyer-room/{token}/message     — send chat message, get assistant reply
  POST /api/buyer-room/{token}/accept      — explicit buyer-accept (rare; mediator usually handles it)

Every message turn persists as two ReplayEvents (user turn + assistant turn)
so the admin drawer can reconstruct the transcript.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, async_session
from app.gateway.adapters.product_adapter import (
    AgentProductFilters,
    list_products_for_agent,
)
from app.gateway.buyer_mediator import (
    BuyerMediatorService,
    get_session,
    new_session,
)
from app.gateway.buyer_mediator.session import BuyerSession
from app.models.deal_share_token import DealShareToken
from app.models.replay_event import EVENT_BUYER_ROOM_MESSAGE, ReplayEvent
from app.models.tenant import Tenant
from app.schemas.buyer_room import (
    BuyerRoomContext,
    BuyerRoomMessageRequest,
    BuyerRoomMessageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/buyer-room", tags=["buyer-room"])

_service = BuyerMediatorService()


async def _resolve_token(db: AsyncSession, token: str) -> tuple[DealShareToken, Tenant]:
    now = datetime.now(timezone.utc)
    row = (await db.execute(
        select(DealShareToken).where(DealShareToken.token == token)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="share link not found")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=410, detail="share link expired")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == row.seller_tenant_id)
    )).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=500, detail="tenant missing for token")

    row.last_used_at = now
    await db.flush()
    return row, tenant


async def _log_message_event(
    *, tenant_id_uuid: str, session: BuyerSession, role: str, content: str, offer_id: str | None = None,
    tool_calls: list | None = None,
) -> None:
    async with async_session() as db:
        db.add(ReplayEvent(
            tenant_id=tenant_id_uuid,
            event_type=EVENT_BUYER_ROOM_MESSAGE,
            offer_id=offer_id,
            document_log_id=None,
            principal_id=f"buyer-room:{session.session_id}",
            payload=json.dumps({
                "session_id": session.session_id,
                "share_token_prefix": session.token[:8] if session.token else "",
                "role": role,
                "content": content[:8000],
                "tool_calls": tool_calls or [],
            }, default=str),
        ))
        await db.commit()


@router.get("/{token}/context", response_model=BuyerRoomContext)
async def context(token: str, db: AsyncSession = Depends(get_db)) -> BuyerRoomContext:
    share, tenant = await _resolve_token(db, token)
    await db.commit()

    products = await list_products_for_agent(
        tenant_slug=tenant.slug,
        principal_id=f"buyer-room:{share.token[:8]}",
        filters=AgentProductFilters(limit=50),
    )

    session = await new_session(token=token, tenant_slug=tenant.slug)

    greeting_turn = await _service.greet(
        session, seller_name=tenant.name, product_names=[p["name"] for p in products],
    )
    # Persist the opening greeting so the admin transcript is complete.
    await _log_message_event(
        tenant_id_uuid=tenant.id,
        session=session,
        role="assistant",
        content=greeting_turn.assistant_text,
    )

    return BuyerRoomContext(
        session_id=session.session_id,
        seller_name=tenant.name,
        products=products,
        greeting=greeting_turn.assistant_text,
    )


@router.post("/{token}/message", response_model=BuyerRoomMessageResponse)
async def send_message(
    token: str,
    payload: BuyerRoomMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> BuyerRoomMessageResponse:
    share, tenant = await _resolve_token(db, token)
    await db.commit()

    session = await get_session(payload.session_id)
    if session is None or session.token != token:
        raise HTTPException(status_code=404, detail="session not found; reload the page")

    # Log the user turn immediately — separate DB session so it persists
    # even if Claude blows up mid-call.
    await _log_message_event(
        tenant_id_uuid=tenant.id, session=session, role="user", content=payload.content,
    )

    try:
        turn = await _service.turn(session, seller_name=tenant.name, user_message=payload.content)
    except Exception as e:    # noqa: BLE001 — surface as graceful error
        logger.exception("buyer_mediator turn failed")
        await _log_message_event(
            tenant_id_uuid=tenant.id, session=session,
            role="assistant",
            content=f"(mediator error: {str(e)[:200]})",
        )
        raise HTTPException(status_code=502, detail="mediator unavailable") from e

    offer_id = session.offer.offer_id if session.offer else None
    await _log_message_event(
        tenant_id_uuid=tenant.id,
        session=session,
        role="assistant",
        content=turn.assistant_text,
        offer_id=offer_id,
        tool_calls=turn.tool_calls,
    )

    return BuyerRoomMessageResponse(
        assistant_text=turn.assistant_text,
        offer_state=turn.offer_state,
        tool_calls=turn.tool_calls,
    )
