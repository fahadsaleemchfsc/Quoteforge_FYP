from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)        # Proposal | Quote
    format = Column(String(10), nullable=False)       # PDF | DOCX
    status = Column(String(20), default="draft")      # active | draft | archived
    content = Column(Text, default="")                # template body / instructions
    file_path = Column(String(500), default="")
    usage_count = Column(Integer, default=0)
    author = Column(String(120), default="Admin")
    last_modified = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Master HTML template — when is_master=True and html_body is set,
    # quote generation renders through Jinja2 + xhtml2pdf instead of the
    # legacy ReportLab section pipeline. One master per tenant; the
    # /api/templates/master endpoints upsert this row.
    html_body = Column(Text, default="")
    is_master = Column(Boolean, default=False, index=True)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )
    tenant = relationship("Tenant", lazy="joined")
