from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class CRMConnection(Base):
    __tablename__ = "crm_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Nullable at the schema level so migrate_add_crm_connections_tenant_id
    # can ALTER existing rows and backfill them to the default tenant.
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    tenant = relationship("Tenant", lazy="joined")
    platform = Column(String(50), nullable=False)     # Salesforce | HubSpot | Custom
    environment = Column(String(50), default="sandbox")  # sandbox | production
    status = Column(String(20), default="disconnected")  # connected | disconnected
    oauth_tokens = Column(Text, default="")           # encrypted JSON
    api_key = Column(String(500), default="")
    deals_count = Column(Integer, default=0)
    health = Column(Float, default=0.0)
    last_synced = Column(DateTime, nullable=True)
    field_mappings = Column(Text, default="[]")       # JSON array
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
