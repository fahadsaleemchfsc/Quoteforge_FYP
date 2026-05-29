from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # admin | user
    department = Column(String(100), default="")
    status = Column(String(20), default="active")  # active | inactive
    avatar = Column(String(10), default="")
    quotes_generated = Column(Integer, default=0)
    last_login = Column(DateTime(timezone=True), nullable=True)
    # Nullable at the schema level so the migrate_add_user_tenant_id ALTER is
    # safe on existing rows; get_current_tenant_id 403s if it lands as NULL.
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    tenant = relationship("Tenant", lazy="joined")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
