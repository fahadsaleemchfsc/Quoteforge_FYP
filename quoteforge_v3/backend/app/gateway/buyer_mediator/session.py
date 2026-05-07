"""
In-process session store for buyer-room chats.

State we keep per session:
  - chat history (Anthropic Messages API shape)
  - the seller's tenant slug
  - the current signed offer (offer_id + signature + payload), if one has
    been created — so accept_current_offer can commit without the buyer
    ever seeing the signature

A session is created on the first GET /api/buyer-room/{token}/context call
and lives in memory. Max size is bounded by MAX_SESSIONS; oldest get evicted.

TODO(phase-2): move to Redis so sessions survive restarts + horizontal scale.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

MAX_SESSIONS = 1000
SESSION_TTL_SECONDS = 60 * 60 * 6     # 6 hours


@dataclass
class OfferState:
    offer_id: str
    signature: str
    payload: dict[str, Any]
    requires_approval: bool
    created_at: float


@dataclass
class BuyerSession:
    session_id: str
    token: str
    tenant_slug: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    offer: OfferState | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_active = time.monotonic()


_sessions: "OrderedDict[str, BuyerSession]" = OrderedDict()
_lock = asyncio.Lock()


def _evict_expired() -> None:
    now = time.monotonic()
    stale = [sid for sid, s in _sessions.items() if now - s.last_active > SESSION_TTL_SECONDS]
    for sid in stale:
        _sessions.pop(sid, None)
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)


async def new_session(token: str, tenant_slug: str) -> BuyerSession:
    async with _lock:
        _evict_expired()
        session_id = f"br_{secrets.token_urlsafe(18)}"
        s = BuyerSession(session_id=session_id, token=token, tenant_slug=tenant_slug)
        _sessions[session_id] = s
        return s


async def get_session(session_id: str) -> BuyerSession | None:
    async with _lock:
        s = _sessions.get(session_id)
        if s is None:
            return None
        if time.monotonic() - s.last_active > SESSION_TTL_SECONDS:
            _sessions.pop(session_id, None)
            return None
        s.touch()
        _sessions.move_to_end(session_id)
        return s
