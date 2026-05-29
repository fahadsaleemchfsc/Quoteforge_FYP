from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, default="")
    category = Column(String(50), default="general")  # general | ai | email | security
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
