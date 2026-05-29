"""Business actions executed against a tenant's connected Salesforce org.

These endpoints live alongside the OAuth flow but are split out so the
OAuth module stays focused on the auth dance. Every call goes through
`sf_request`, so token refresh + tenant isolation are handled centrally.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant_id
from app.integrations.salesforce_client import sf_request
from app.models.document_log import DocumentLog

router = APIRouter(prefix="/integrations/salesforce", tags=["salesforce-actions"])
_logger = logging.getLogger(__name__)

# Salesforce REST API version we target. v60.0 (Spring '24) is widely
# available and ships standard sObjects we use here.
_SF_API_VERSION = "v60.0"


class PushQuoteRequest(BaseModel):
    doc_id: str = Field(..., description="QuoteForge document id, e.g. DOC-2457")
    opportunity_id: str = Field(
        ...,
        description="Salesforce Opportunity Id (15 or 18 char) to attach the Quote to",
    )


@router.post("/push-quote")
async def push_quote(
    body: PushQuoteRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a standard Salesforce Quote linked to the given Opportunity.

    The QuoteForge DocumentLog supplies the human-readable Name and an
    expiration date. We deliberately don't create QuoteLineItems here —
    that requires OpportunityLineItems to already exist with PricebookEntry
    Ids, which is org-specific. Returning the Quote Id lets the caller
    add line items in a follow-up call if needed.
    """
    # Resolve the QuoteForge document for the calling tenant. user_id is
    # nullable on DocumentLog but tenant scoping comes via the User row,
    # so for now we just confirm the doc exists; multi-tenant scoping on
    # documents lives in app/routers/quotes.py and isn't tightened here.
    doc_result = await db.execute(
        select(DocumentLog).where(DocumentLog.doc_id == body.doc_id)
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"QuoteForge document {body.doc_id!r} not found",
        )

    expiration = (
        doc.valid_until
        or datetime.now(timezone.utc) + timedelta(days=30)
    )
    payload = {
        "Name": doc.deal_name or f"QuoteForge {doc.doc_id}",
        "OpportunityId": body.opportunity_id,
        "ExpirationDate": expiration.date().isoformat(),
    }

    resp = await sf_request(
        db,
        tenant_id,
        "POST",
        f"/services/data/{_SF_API_VERSION}/sobjects/Quote",
        json=payload,
    )
    if resp.status_code >= 400:
        # Surface Salesforce's error verbatim — it's almost always
        # actionable ("FIELD_INTEGRITY_EXCEPTION: insufficient access...").
        _logger.warning(
            "Salesforce Quote create failed: %s %s",
            resp.status_code,
            resp.text,
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Salesforce rejected the Quote create: {resp.text}",
        )

    created = resp.json()
    sf_quote_id = created.get("id")

    # Persist the SF id back to the DocumentLog so the LWC can deep-link
    # to the record without re-querying.
    doc.crm_external_id = sf_quote_id
    doc.crm_synced_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "ok": True,
        "doc_id": body.doc_id,
        "salesforce_quote_id": sf_quote_id,
        "salesforce_response": created,
    }
