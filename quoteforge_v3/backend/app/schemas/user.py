from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    department: str
    status: str
    avatar: str
    quotes_generated: int
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserInvite(BaseModel):
    email: EmailStr
    name: str
    role: str = "user"
    department: str = ""


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    status: Optional[str] = None
