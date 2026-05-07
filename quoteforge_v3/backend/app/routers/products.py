"""
Admin-side products router.

Used by the React admin portal. This is the seller's catalog control surface —
they create SKUs, set base/floor prices, and flip agent_exposed per product.

Separate from the MCP `get_products` tool: the admin endpoint returns ALL
products including `min_price_floor` and `metadata`; the MCP tool redacts
both. Keeping these two surfaces distinct prevents a future refactor from
leaking internal fields to buyer agents.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id, get_current_user
from app.models.product import Product
from app.models.user import User
from app.schemas.product import (
    AgentExposureToggle,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


def _to_out(p: Product) -> ProductOut:
    try:
        metadata = json.loads(p.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return ProductOut(
        id=p.id,
        tenant_id=p.tenant_id,
        sku=p.sku,
        name=p.name,
        description=p.description,
        category=p.category,
        base_price=p.base_price,
        min_price_floor=p.min_price_floor,
        currency=p.currency,
        unit=p.unit,
        agent_exposed=p.agent_exposed,
        metadata=metadata,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=list[ProductOut])
async def list_products(
    search: str = Query(default=""),
    category: str | None = Query(default=None),
    agent_exposed: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> list[ProductOut]:
    stmt = select(Product).where(Product.tenant_id == tenant_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((Product.sku.ilike(like)) | (Product.name.ilike(like)))
    if category:
        stmt = stmt.where(Product.category == category)
    if agent_exposed is not None:
        stmt = stmt.where(Product.agent_exposed == agent_exposed)
    stmt = stmt.order_by(Product.name)

    result = await db.execute(stmt)
    return [_to_out(p) for p in result.scalars().all()]


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ProductOut:
    product = Product(
        tenant_id=tenant_id,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        base_price=payload.base_price,
        min_price_floor=payload.min_price_floor,
        currency=payload.currency,
        unit=payload.unit,
        agent_exposed=payload.agent_exposed,
        metadata_json=json.dumps(payload.metadata),
    )
    db.add(product)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"SKU '{payload.sku}' already exists for this tenant")
    await db.refresh(product)
    logger.info("product created sku=%s tenant=%s by user=%s", product.sku, tenant_id, user.email)
    return _to_out(product)


async def _get_or_404(db: AsyncSession, tenant_id: str, product_id: str) -> Product:
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ProductOut:
    product = await _get_or_404(db, tenant_id, product_id)

    updates = payload.model_dump(exclude_unset=True)
    if "metadata" in updates:
        product.metadata_json = json.dumps(updates.pop("metadata"))
    for field, value in updates.items():
        setattr(product, field, value)

    # Enforce the floor <= base invariant across partial updates too.
    if Decimal(product.min_price_floor) > Decimal(product.base_price):
        await db.rollback()
        raise HTTPException(status_code=422, detail="min_price_floor must be <= base_price")

    await db.commit()
    await db.refresh(product)
    logger.info("product updated id=%s by user=%s fields=%s", product.id, user.email, list(updates))
    return _to_out(product)


@router.patch("/{product_id}/agent-exposure", response_model=ProductOut)
async def toggle_agent_exposure(
    product_id: str,
    payload: AgentExposureToggle,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> ProductOut:
    """Row-level toggle — the seller's primary control over the MCP surface."""
    product = await _get_or_404(db, tenant_id, product_id)
    product.agent_exposed = payload.agent_exposed
    await db.commit()
    await db.refresh(product)
    logger.info(
        "product agent_exposed=%s id=%s sku=%s by user=%s",
        payload.agent_exposed, product.id, product.sku, user.email,
    )
    return _to_out(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> None:
    product = await _get_or_404(db, tenant_id, product_id)
    await db.delete(product)
    await db.commit()
    logger.info("product deleted id=%s sku=%s by user=%s", product_id, product.sku, user.email)
