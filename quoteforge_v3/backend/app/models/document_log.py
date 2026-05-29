from sqlalchemy import Column, Integer, String, DateTime, Text, Float, func
from app.core.database import Base


class DocumentLog(Base):
    __tablename__ = "document_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(20), unique=True, nullable=False)  # DOC-XXXX
    deal_id = Column(String(100), default="")
    client = Column(String(255), default="")
    deal_name = Column(String(255), default="")
    type = Column(String(50), default="Quote")                # Quote | Proposal
    format = Column(String(10), default="PDF")                # PDF | DOCX
    template_id = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")            # pending | generated | delivered | failed
    delivery_status = Column(String(20), default="pending")
    file_path = Column(String(500), default="")
    amount = Column(Float, default=0.0)
    compliance_framework = Column(String(100), default="")
    generation_time = Column(Float, default=0.0)              # seconds
    metadata_json = Column(Text, default="{}")
    user_id = Column(Integer, nullable=True)
    user_name = Column(String(120), default="")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)  # Proposal expiration date
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # CRM sync bookkeeping — populated by crm_sync_worker after successful push.
    crm_synced_at = Column(DateTime(timezone=True), nullable=True)
    crm_external_id = Column(String(64), nullable=True)  # Salesforce QuoteForge_Document__c Id
