from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TemplateOut(BaseModel):
    id: int
    name: str
    type: str
    format: str
    status: str
    content: str
    usage_count: int
    author: str
    lastModified: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TemplateCreate(BaseModel):
    name: str
    type: str
    format: str = "PDF"
    status: str = "draft"
    content: str = ""
    author: str = "Admin"


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    content: Optional[str] = None
