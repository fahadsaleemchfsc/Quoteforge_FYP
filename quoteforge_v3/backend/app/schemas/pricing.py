from pydantic import BaseModel
from typing import Optional


class PricingRuleOut(BaseModel):
    id: int
    name: str
    type: str
    condition: str
    value: str
    region: str
    status: str

    class Config:
        from_attributes = True


class PricingRuleCreate(BaseModel):
    name: str
    type: str
    condition: str = ""
    value: str = ""
    region: str = "Global"
    status: str = "active"


class PricingRuleUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    condition: Optional[str] = None
    value: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
