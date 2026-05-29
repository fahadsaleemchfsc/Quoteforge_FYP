from sqlalchemy import Column, Integer, String, DateTime, func
from app.core.database import Base


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)       # Discount | Tax | Compliance
    condition = Column(String(255), default="")
    value = Column(String(100), default="")
    region = Column(String(50), default="Global")
    status = Column(String(20), default="active")   # active | inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
