"""
Per-tenant token-bucket rate limiter.

Final implementation (next step): atomic Lua script against Redis — one
bucket per (tenant_id, tier). Free tier: 100 req/min, paid: 1000 req/min.

Current (dev-stub) implementation: in-process best-effort counter. Correct for
single-process dev; NOT safe under gunicorn with workers>1. Replaced in the
Redis step.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.gateway.auth.deps import MCPPrincipal


@dataclass
class _Bucket:
    tokens: float
    updated: float


# In-process state — replaced by Redis.
_buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(tokens=0.0, updated=0.0))

FREE_RPM = 100
PAID_RPM = 1000


def _limits_for(principal: MCPPrincipal) -> tuple[float, float]:
    """Return (capacity, refill_per_second)."""
    rpm = PAID_RPM if "tier:paid" in principal.scopes else FREE_RPM
    return float(rpm), rpm / 60.0


async def enforce_rate_limit(principal: MCPPrincipal) -> None:
    key = f"rl:{principal.tenant_id}"
    capacity, refill = _limits_for(principal)

    now = time.monotonic()
    bucket = _buckets[key]
    if bucket.updated == 0.0:
        bucket.tokens = capacity
    else:
        bucket.tokens = min(capacity, bucket.tokens + (now - bucket.updated) * refill)
    bucket.updated = now

    if bucket.tokens < 1.0:
        retry_after = max(1, int((1.0 - bucket.tokens) / refill))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limit exceeded for tenant {principal.tenant_id}",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.tokens -= 1.0
