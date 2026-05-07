"""
OfferContext builders — convert live shapes (resolved product dicts, or a
persisted DocumentLog) into the pure-data OfferContext the engine expects.

Two paths:

  * `from_resolved_lines(...)`: called at request_quote time when we already
    have ResolvedExposedProduct instances in hand.
  * `from_document_log(db, doc)`: called at accept_offer time when we need to
    re-fetch product data fresh (so admin-tightened floors or edits take
    effect on re-evaluation).
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.adapters.product_adapter import ResolvedExposedProduct
from app.gateway.guardrails.engine import LineItemContext, OfferContext
from app.gateway.money import dollars_to_cents
from app.models.document_log import DocumentLog
from app.models.product import Product
from app.models.tenant import Tenant


def _cents_from_decimal(value) -> int:
    return dollars_to_cents(value)


def from_resolved_lines(
    *,
    tenant_id_uuid: str,
    buyer_region: str,
    currency: str,
    resolved: dict[str, ResolvedExposedProduct],
    line_order: Iterable[tuple[str, int]],       # [(sku, quantity), ...] preserves order
    total_cents: int,
) -> OfferContext:
    """Build an OfferContext from data we already have in memory.

    `resolved` is keyed by SKU; `line_order` gives the order the buyer
    requested and supplies the quantity. Unit_price comes from the resolved
    product (authoritative — the buyer never sets prices in request_quote).
    """
    items: list[LineItemContext] = []
    for sku, qty in line_order:
        product = resolved[sku]
        items.append(LineItemContext(
            sku=sku,
            quantity=qty,
            unit_price_cents=_cents_from_decimal(product.base_price),
            base_price_cents=_cents_from_decimal(product.base_price),
            min_price_floor_cents=_cents_from_decimal(product.min_price_floor),
        ))
    return OfferContext(
        tenant_id=tenant_id_uuid,
        line_items=tuple(items),
        total_cents=total_cents,
        currency=currency,
        buyer_region=buyer_region,
    )


async def from_document_log(
    db: AsyncSession,
    doc: DocumentLog,
) -> OfferContext | None:
    """
    Rebuild OfferContext from a persisted draft. Re-reads products fresh — if
    the admin raised a floor between quote and accept, the new floor is used.

    Returns None if the stored offer payload is missing or malformed, or if
    the tenant can't be resolved — callers treat None as a data-integrity
    failure and refuse to proceed.
    """
    try:
        meta = json.loads(doc.metadata_json or "{}")
    except json.JSONDecodeError:
        return None
    payload = meta.get("offer_payload")
    if not isinstance(payload, dict):
        return None

    tenant_slug = meta.get("tenant_slug")
    if not tenant_slug:
        return None
    tenant_row = (
        await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant_row is None:
        return None

    # Pull fresh product data keyed by SKU.
    line_items_raw = payload.get("line_items", []) or []
    skus = [li["sku"] for li in line_items_raw if "sku" in li]
    if not skus:
        return None
    products = (
        await db.execute(
            select(Product).where(
                Product.tenant_id == tenant_row.id,
                Product.sku.in_(skus),
            )
        )
    ).scalars().all()
    by_sku: dict[str, Product] = {p.sku: p for p in products}

    items: list[LineItemContext] = []
    for li in line_items_raw:
        sku = li.get("sku")
        qty = int(li.get("quantity", 0))
        if not sku or qty <= 0:
            return None
        product = by_sku.get(sku)
        if product is None:
            # SKU was removed from catalog since quote — engine should block.
            # Represent as a zero-floor, zero-base item so MarginCheck fires.
            items.append(LineItemContext(
                sku=sku, quantity=qty,
                unit_price_cents=_cents_from_decimal(li.get("unit_price", 0)),
                base_price_cents=0,
                min_price_floor_cents=_cents_from_decimal(li.get("unit_price", 0)) + 1,
            ))
            continue
        items.append(LineItemContext(
            sku=sku,
            quantity=qty,
            unit_price_cents=_cents_from_decimal(li.get("unit_price", 0)),
            base_price_cents=_cents_from_decimal(product.base_price),
            min_price_floor_cents=_cents_from_decimal(product.min_price_floor),
        ))

    pricing = payload.get("pricing", {})
    total_cents = int(pricing.get("total_cents") or _cents_from_decimal(pricing.get("total", 0)))
    currency = pricing.get("currency", "USD")
    region = payload.get("region", "US")

    return OfferContext(
        tenant_id=tenant_row.id,
        line_items=tuple(items),
        total_cents=total_cents,
        currency=currency,
        buyer_region=region,
    )
