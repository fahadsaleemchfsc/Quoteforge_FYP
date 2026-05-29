from sqlalchemy import Column, Integer, String, DateTime, Text, func
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    user_name = Column(String(120), default="")
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), default="")
    entity_id = Column(String(50), default="")
    details = Column(Text, default="{}")
    ip_address = Column(String(50), default="")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
