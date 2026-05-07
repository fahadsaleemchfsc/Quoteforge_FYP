"""
Quotes Router — the orchestration endpoint that ties all modules together.
End-to-end: CRM data → Pricing Engine → AI Generation → Document Rendering → Logging
"""
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.core.database import get_db
from app.core.security import get_current_tenant_id, get_current_user
from app.models.user import User
from app.models.document_log import DocumentLog
from app.models.audit_log import AuditLog
from app.schemas.quote import GenerateRequest
from app.services.pricing_engine import apply_pricing_rules
from app.services.ai_service import generate_proposal_sections
from app.services.document_engine import render_pdf, render_docx
from app.services.delivery_service import send_document_email
from app.services.crm_service import get_deal_by_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quotes", tags=["quotes"])


async def _next_doc_id(db: AsyncSession, tenant_id: str) -> str:
    """
    Atomic per-tenant doc_id counter — matches the gateway's request_quote path.
    The legacy count-based generator collided with gateway-generated DOC-N ids
    (both live in the same document_logs table) and raised UNIQUE constraint
    errors on insert. Delegating to next_doc_id makes both paths share a
    single monotonic counter per tenant.
    """
    from app.gateway.adapters.doc_id import next_doc_id as _gateway_next
    return await _gateway_next(db, tenant_id)


@router.post("/generate")
async def generate_quote(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
):
    start = time.time()

    # Step 1: Gather deal data (from request or CRM)
    deal_data = {
        "deal_id": req.deal_id,
        "client_name": req.client_name,
        "deal_name": req.deal_name,
        "deal_amount": req.deal_amount,
        "contact_email": req.contact_email,
        "region": req.region,
        "line_items": [item.model_dump() for item in req.line_items],
    }

    # If deal_id provided, try to fetch from CRM demo data
    if req.deal_id and not req.client_name:
        crm_deal = get_deal_by_id(req.deal_id)
        if crm_deal:
            deal_data.update(crm_deal)

    if not deal_data.get("client_name"):
        raise HTTPException(status_code=400, detail="Client name is required")

    # Step 2: Apply pricing rules
    pricing = await apply_pricing_rules(
        db,
        deal_amount=deal_data.get("deal_amount", 0) or sum(
            item.get("unit_price", 0) * item.get("quantity", 1)
            for item in deal_data.get("line_items", [])
        ),
        region=deal_data.get("region", "US"),
        line_items=deal_data.get("line_items", []),
    )

    # Step 3: Prepare context for AI generation
    ai_context = {
        **deal_data,
        "subtotal": pricing["subtotal"],
        "discount": pricing["discount"],
        "tax": pricing["tax"],
        "total": pricing["total"],
        "compliance_framework": pricing["compliance_framework"],
        "compliance_clauses": "\n".join(c["clause"] for c in pricing["compliance_clauses"]),
    }

    # Step 4: AI content generation
    sections = await generate_proposal_sections(db, ai_context)

    # Step 5: Document rendering
    doc_id = await _next_doc_id(db, tenant_id)
    doc_type = "Proposal" if req.output_format == "PDF" else "Quote"

    # Proposal validity: 30 days from generation
    from datetime import timedelta
    generated_at = datetime.now(timezone.utc)
    valid_until = generated_at + timedelta(days=30)

    render_context = {
        **deal_data,
        "type": doc_type,
        "generated_at": generated_at,
        "valid_until": valid_until,
    }

    if req.output_format.upper() == "DOCX":
        file_path = render_docx(doc_id, sections, pricing, render_context)
    else:
        file_path = render_pdf(doc_id, sections, pricing, render_context)

    generation_time = round(time.time() - start, 2)

    # Step 6: Log generation
    doc_log = DocumentLog(
        doc_id=doc_id,
        deal_id=deal_data.get("deal_id", ""),
        client=deal_data["client_name"],
        deal_name=deal_data.get("deal_name", ""),
        type=doc_type,
        format=req.output_format.upper(),
        template_id=req.template_id,
        status="generated",
        delivery_status="pending",
        file_path=file_path,
        amount=pricing["total"],
        compliance_framework=pricing["compliance_framework"],
        generation_time=generation_time,
        valid_until=valid_until,
        user_id=current_user.id,
        user_name=current_user.name,
    )
    db.add(doc_log)

    # Update user's quote count
    current_user.quotes_generated = (current_user.quotes_generated or 0) + 1

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        user_name=current_user.name,
        action="quote_generated",
        entity_type="document",
        entity_id=doc_id,
        details=f"Generated {doc_type} for {deal_data['client_name']} — ${pricing['total']:,.2f}",
    )
    db.add(audit)
    await db.commit()

    return {
        "doc_id": doc_id,
        "status": "generated",
        "type": doc_type,
        "format": req.output_format.upper(),
        "client": deal_data["client_name"],
        "deal_name": deal_data.get("deal_name", ""),
        "pricing": pricing,
        "sections": list(sections.keys()),
        "generation_time": generation_time,
        "generated_at": generated_at.isoformat(),
        "valid_until": valid_until.isoformat(),
        "validity_days": 30,
        "message": f"Document {doc_id} generated in {generation_time}s, valid until {valid_until.strftime('%B %d, %Y')}",
    }


@router.get("/status/{job_id}")
async def get_status(job_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(DocumentLog).where(DocumentLog.doc_id == job_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"doc_id": doc.doc_id, "status": doc.status, "generation_time": doc.generation_time}


@router.get("/documents")
async def list_documents(
    search: str = Query(""),
    status: str = Query(""),
    page: int = Query(1),
    per_page: int = Query(10),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    query = select(DocumentLog)
    if search:
        query = query.where(
            DocumentLog.client.ilike(f"%{search}%") | DocumentLog.doc_id.ilike(f"%{search}%")
        )
    if status and status.lower() not in ("", "all"):
        query = query.where(DocumentLog.status == status)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    query = query.order_by(desc(DocumentLog.id)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    docs = result.scalars().all()

    return {
        "documents": [
            {
                "id": d.doc_id,
                "client": d.client,
                "type": d.type,
                "format": d.format,
                "status": d.status,
                "generatedAt": d.generated_at.strftime("%b %d, %I:%M %p") if d.generated_at else "",
                "deliveredAt": d.delivered_at.strftime("%b %d, %I:%M %p") if d.delivered_at else "—",
                "user": d.user_name,
                "amount": d.amount,
            }
            for d in docs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(DocumentLog).where(DocumentLog.doc_id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc or not doc.file_path:
        raise HTTPException(status_code=404, detail="Document not found")
    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    media = "application/pdf" if doc.format == "PDF" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(str(file_path), media_type=media, filename=file_path.name)


@router.post("/documents/{doc_id}/resend")
async def resend_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await send_document_email(db, doc_id, user_id=current_user.id, user_name=current_user.name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Delivery failed"))
    return result


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    total_docs = (await db.execute(select(func.count(DocumentLog.id)))).scalar() or 0
    delivered = (await db.execute(
        select(func.count(DocumentLog.id)).where(DocumentLog.status == "delivered")
    )).scalar() or 0
    avg_time = (await db.execute(
        select(func.avg(DocumentLog.generation_time)).where(DocumentLog.generation_time > 0)
    )).scalar() or 0

    conversion = round((delivered / total_docs * 100), 1) if total_docs > 0 else 0

    return {
        "quotesGenerated": total_docs,
        "proposalsSent": delivered,
        "conversionRate": f"{conversion}%",
        "avgGenTime": f"{avg_time:.1f}s",
    }


@router.get("/chart")
async def get_chart_data(_=Depends(get_current_user)):
    # Return realistic chart data
    return [
        {"month": "Jul", "quotes": 145, "proposals": 98, "conversions": 62},
        {"month": "Aug", "quotes": 178, "proposals": 121, "conversions": 79},
        {"month": "Sep", "quotes": 162, "proposals": 108, "conversions": 71},
        {"month": "Oct", "quotes": 201, "proposals": 142, "conversions": 95},
        {"month": "Nov", "quotes": 189, "proposals": 131, "conversions": 88},
        {"month": "Dec", "quotes": 223, "proposals": 156, "conversions": 104},
        {"month": "Jan", "quotes": 247, "proposals": 172, "conversions": 118},
    ]


@router.get("/activity")
async def get_activity(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(DocumentLog).order_by(desc(DocumentLog.id)).limit(10)
    )
    docs = result.scalars().all()

    if not docs:
        # Return seed activity data
        return [
            {"id": 1, "type": "quote", "client": "Acme Corp", "deal": "Enterprise License", "amount": "$45,000", "status": "delivered", "time": "2 min ago", "user": "Sarah J."},
            {"id": 2, "type": "proposal", "client": "TechStart Inc", "deal": "SaaS Platform", "amount": "$128,000", "status": "generated", "time": "15 min ago", "user": "Mike R."},
            {"id": 3, "type": "quote", "client": "Global Traders", "deal": "Consulting Package", "amount": "$22,500", "status": "pending", "time": "1 hr ago", "user": "Lisa K."},
            {"id": 4, "type": "proposal", "client": "Nexus Systems", "deal": "Infrastructure", "amount": "$89,000", "status": "delivered", "time": "2 hrs ago", "user": "James W."},
            {"id": 5, "type": "quote", "client": "Pinnacle Health", "deal": "Data Analytics", "amount": "$67,200", "status": "failed", "time": "3 hrs ago", "user": "Sarah J."},
        ]

    return [
        {
            "id": d.id,
            "type": d.type.lower(),
            "client": d.client,
            "deal": d.deal_name,
            "amount": f"${d.amount:,.0f}",
            "status": d.status,
            "time": d.generated_at.strftime("%b %d, %I:%M %p") if d.generated_at else "",
            "user": d.user_name,
        }
        for d in docs
    ]
