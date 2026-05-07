"""
Product adapter — the seam between MCP tools and the Product model.

Two jobs:
  1. list_products_for_agent: filtered catalog query, agent_exposed ONLY,
     minus internal fields (min_price_floor, metadata).
  2. resolve_exposed_sku: used by request_quote to look up a SKU and refuse
     anything not marked agent_exposed.

Both paths write a light-weight Replay Layer entry capturing the call shape
without payloads — payload detail belongs in the tool-specific log events.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

MAX_LIMIT = 200
DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class AgentProductFilters:
    category: str | None = None
    max_price: Decimal | None = None
    currency: str | None = None
    limit: int = DEFAULT_LIMIT


async def _resolve_tenant_id(db: AsyncSession, tenant_slug: str) -> str | None:
    """Slug → UUID. Returns None when the slug has no tenant row."""
    result = await db.execute(select(Tenant.id).where(Tenant.slug == tenant_slug))
    return result.scalar_one_or_none()


def _redact_for_agent(p: Product) -> dict[str, Any]:
    """Shape a Product row for MCP output. NEVER include min_price_floor or metadata."""
    return {
        "sku": p.sku,
        "name": p.name,
        "description": p.description or "",
        "category": p.category or "",
        "base_price": float(p.base_price),
        "currency": p.currency,
        "unit": p.unit,
    }


async def _log_replay(
    db: AsyncSession,
    *,
    tenant_slug: str,
    principal_id: str,
    action: str,
    entity_id: str,
    details: str,
) -> None:
    db.add(AuditLog(
        user_id=None,
        user_name=f"mcp:{principal_id}",
        action=action,
        entity_type="gateway_call",
        entity_id=entity_id,
        details=f"tenant={tenant_slug} {details}",
    ))


async def list_products_for_agent(
    *,
    tenant_slug: str,
    principal_id: str,
    filters: AgentProductFilters,
) -> list[dict[str, Any]]:
    limit = max(1, min(filters.limit, MAX_LIMIT))

    async with async_session() as db:
        tenant_id = await _resolve_tenant_id(db, tenant_slug)
        if tenant_id is None:
            # Unknown tenant → empty result, log for replay. Don't leak existence.
            await _log_replay(
                db, tenant_slug=tenant_slug, principal_id=principal_id,
                action="get_products", entity_id="n/a",
                details="result=0 reason=unknown_tenant",
            )
            await db.commit()
            return []

        stmt = (
            select(Product)
            .where(Product.tenant_id == tenant_id, Product.agent_exposed.is_(True))
        )
        if filters.category:
            stmt = stmt.where(Product.category == filters.category)
        if filters.currency:
            stmt = stmt.where(Product.currency == filters.currency)
        if filters.max_price is not None:
            stmt = stmt.where(Product.base_price <= filters.max_price)
        stmt = stmt.order_by(Product.name).limit(limit)

        result = await db.execute(stmt)
        products = result.scalars().all()
        redacted = [_redact_for_agent(p) for p in products]

        await _log_replay(
            db, tenant_slug=tenant_slug, principal_id=principal_id,
            action="get_products", entity_id=f"count={len(redacted)}",
            details=(
                f"result={len(redacted)} "
                f"category={filters.category or '-'} "
                f"currency={filters.currency or '-'} "
                f"max_price={filters.max_price or '-'} "
                f"limit={limit}"
            ),
        )
        await db.commit()

    logger.info(
        "get_products tenant=%s principal=%s results=%d",
        tenant_slug, principal_id, len(redacted),
    )
    return redacted


@dataclass(frozen=True)
class ResolvedExposedProduct:
    id: str
    sku: str
    name: str
    base_price: Decimal
    min_price_floor: Decimal          # retained for Guardrail Engine — caller must not echo
    currency: str
    unit: str
    description: str


async def resolve_exposed_skus(
    *,
    tenant_slug: str,
    skus: list[str],
) -> dict[str, ResolvedExposedProduct]:
    """
    Look up the given SKUs under the tenant, return only ones that are
    agent_exposed=True. Missing / non-exposed SKUs are simply absent from
    the result; the caller raises MCPError with the omitted set.
    """
    async with async_session() as db:
        tenant_id = await _resolve_tenant_id(db, tenant_slug)
        if tenant_id is None:
            return {}

        result = await db.execute(
            select(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.agent_exposed.is_(True),
                Product.sku.in_(skus),
            )
        )
        return {
            p.sku: ResolvedExposedProduct(
                id=p.id,
                sku=p.sku,
                name=p.name,
                base_price=Decimal(p.base_price),
                min_price_floor=Decimal(p.min_price_floor),
                currency=p.currency,
                unit=p.unit,
                description=p.description or "",
            )
            for p in result.scalars().all()
        }
