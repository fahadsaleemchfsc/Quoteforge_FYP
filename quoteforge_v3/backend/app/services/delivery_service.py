"""
Delivery Service — sends generated documents via SMTP email
and logs delivery status.
"""
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.document_log import DocumentLog
from app.models.audit_log import AuditLog
from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_document_email(
    db: AsyncSession,
    doc_id: str,
    recipient_email: str = "",
    user_id: int = None,
    user_name: str = "",
) -> dict:
    """Send a generated document as an email attachment."""
    # Find the document
    result = await db.execute(
        select(DocumentLog).where(DocumentLog.doc_id == doc_id)
    )
    doc_log = result.scalar_one_or_none()
    if not doc_log:
        return {"success": False, "error": "Document not found"}

    file_path = doc_log.file_path
    if not file_path or not Path(file_path).exists():
        return {"success": False, "error": "Document file not found on disk"}

    # Try SMTP delivery
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        try:
            import aiosmtplib

            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_FROM
            msg["To"] = recipient_email or "client@example.com"
            msg["Subject"] = f"QuoteForge — {doc_log.type}: {doc_log.deal_name}"

            body = (
                f"Dear {doc_log.client},\n\n"
                f"Please find attached the {doc_log.type.lower()} for {doc_log.deal_name}.\n\n"
                f"Document ID: {doc_id}\n"
                f"Generated: {doc_log.generated_at}\n\n"
                f"Best regards,\nQuoteForge"
            )
            msg.attach(MIMEText(body, "plain"))

            # Attach file
            with open(file_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = Path(file_path).name
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=True,
            )

            doc_log.status = "delivered"
            doc_log.delivery_status = "delivered"
            doc_log.delivered_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(f"Email sent for {doc_id} to {recipient_email}")
            return {"success": True, "message": "Document delivered via email"}

        except Exception as e:
            logger.error(f"SMTP delivery failed: {e}")
            doc_log.delivery_status = "failed"
            await db.commit()
            return {"success": False, "error": f"Email delivery failed: {str(e)}"}
    else:
        # Simulate delivery for demo
        doc_log.status = "delivered"
        doc_log.delivery_status = "delivered"
        doc_log.delivered_at = datetime.now(timezone.utc)
        await db.commit()

        # Audit log
        audit = AuditLog(
            user_id=user_id,
            user_name=user_name,
            action="document_delivered",
            entity_type="document",
            entity_id=doc_id,
            details=f"Document {doc_id} delivered (simulated)",
        )
        db.add(audit)
        await db.commit()

        return {"success": True, "message": "Document delivery simulated (SMTP not configured)"}
