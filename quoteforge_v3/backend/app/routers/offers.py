"""
Dual Output endpoints.

  GET /api/offers/{offer_id}/pdf   — human PDF
  GET /api/offers/{offer_id}/ucp   — UCP 2026-01 JSON

Both look the offer up the same way accept_offer does (via the stored
offer_payload in DocumentLog.metadata_json), and the signature passed to
the UCP renderer is the one we stamped at quote time — never recomputed.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant
from app.gateway.rendering import OfferRenderer
from app.models.document_log import DocumentLog
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/offers", tags=["offers"])


async def _fetch_offer_metadata(db: AsyncSession, offer_id: str) -> tuple[dict, str, str]:
    """
    Return (offer_payload, signature, doc_id) or raise 404.

    Same lookup pattern as quote_adapter.fetch_offer_by_id — LIKE on
    metadata_json until we move to a proper offers table in Phase 2.
    """
    from sqlalchemy import select
    result = await db.execute(
        select(DocumentLog).where(
            DocumentLog.metadata_json.like(f'%"offer_id": "{offer_id}"%')
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="offer not found")
    try:
        meta = json.loads(doc.metadata_json or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail="offer metadata corrupt") from e
    payload = meta.get("offer_payload")
    signature = meta.get("offer_signature", "")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="offer payload missing")
    return payload, signature, doc.doc_id


@router.get("/{offer_id}/pdf")
async def render_offer_pdf(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> Response:
    payload, signature, doc_id = await _fetch_offer_metadata(db, offer_id)
    # The renderer expects the signature accessible as __signature__ for the
    # signature block; we also pass tenant name for the PDF header.
    payload = dict(payload)
    payload["__signature__"] = signature
    pdf_bytes = OfferRenderer().render_pdf(payload, tenant_name=tenant.name)
    logger.info("rendered pdf offer=%s doc=%s size=%d", offer_id, doc_id, len(pdf_bytes))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{doc_id or offer_id}.pdf"',
        },
    )


@router.get("/{offer_id}/ucp")
async def render_offer_ucp(
    offer_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict:
    payload, signature, _doc_id = await _fetch_offer_metadata(db, offer_id)
    return OfferRenderer().render_ucp_json(
        payload, tenant_name=tenant.name, signature=signature,
    )
