from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PromptOut(BaseModel):
    id: int
    name: str
    section: str
    prompt_text: str
    version: str
    status: str
    tokens: str
    last_used: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PromptCreate(BaseModel):
    name: str
    section: str
    prompt_text: str = ""
    version: str = "v1.0"
    status: str = "draft"
    tokens: str = "~0"


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    section: Optional[str] = None
    prompt_text: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    tokens: Optional[str] = None
