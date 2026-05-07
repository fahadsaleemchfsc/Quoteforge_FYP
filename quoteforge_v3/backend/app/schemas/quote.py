from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class LineItem(BaseModel):
    product: str
    quantity: int = 1
    unit_price: float = 0.0
    description: str = ""


class GenerateRequest(BaseModel):
    deal_id: str = ""
    client_name: str = ""
    deal_name: str = ""
    deal_amount: float = 0.0
    contact_email: str = ""
    region: str = "US"
    template_id: Optional[int] = None
    output_format: str = "PDF"
    line_items: List[LineItem] = []
    crm_connection_id: Optional[int] = None


class DocumentOut(BaseModel):
    id: int
    doc_id: str
    client: str
    deal_name: str
    type: str
    format: str
    status: str
    delivery_status: str
    amount: float
    user_name: str
    generated_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    class Config:
        from_attributes = True
