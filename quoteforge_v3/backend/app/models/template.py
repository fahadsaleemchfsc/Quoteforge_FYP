from sqlalchemy import Column, Integer, String, Text, DateTime, func
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
    last_modified = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())
