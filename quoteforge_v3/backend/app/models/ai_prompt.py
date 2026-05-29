from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base


class AIPrompt(Base):
    __tablename__ = "ai_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    section = Column(String(100), nullable=False)     # Cover Letter | Scope | Pricing | Deliverables | Terms | Summary
    prompt_text = Column(Text, default="")
    version = Column(String(20), default="v1.0")
    status = Column(String(20), default="draft")      # active | testing | draft
    tokens = Column(String(20), default="~0")
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
