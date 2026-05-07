from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CRMConnectionOut(BaseModel):
    id: int
    platform: str
    environment: str
    status: str
    deals_count: int
    health: float
    last_synced: Optional[datetime] = None

    class Config:
        from_attributes = True


class CRMConnectRequest(BaseModel):
    platform: str
    environment: str = "sandbox"
    api_key: Optional[str] = None


class FieldMapping(BaseModel):
    crm_field: str
    system_field: str
    type: str = "string"


class FieldMappingsUpdate(BaseModel):
    mappings: List[FieldMapping]
