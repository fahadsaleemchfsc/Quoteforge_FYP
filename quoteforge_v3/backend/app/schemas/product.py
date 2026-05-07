"""Pydantic schemas for the admin products API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    base_price: Decimal = Field(ge=0, decimal_places=2)
    min_price_floor: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    unit: str = Field(default="license", min_length=1, max_length=50)
    agent_exposed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _floor_leq_base(self) -> "ProductBase":
        if self.min_price_floor > self.base_price:
            raise ValueError("min_price_floor must be <= base_price")
        return self


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    """Partial update — all fields optional."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    base_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    min_price_floor: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    agent_exposed: bool | None = None
    metadata: dict[str, Any] | None = None


class AgentExposureToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_exposed: bool


class ProductOut(ProductBase):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
