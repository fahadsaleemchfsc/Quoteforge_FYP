"""
MCP tool: get_products

Returns the seller's agent-accessible catalog. Anything not flipped to
agent_exposed=True by the admin is invisible here — that's the seller's
primary control surface over what buyer agents can see.

Fields deliberately omitted from the output:
  - min_price_floor  (consumed internally by the Guardrail Engine)
  - metadata          (internal notes / flags)
  - agent_exposed     (every row returned is exposed by definition)
  - tenant_id         (inferred from the authenticated principal)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.gateway.adapters.product_adapter import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AgentProductFilters,
    list_products_for_agent,
)
from app.gateway.tools.base import Tool, ToolContext
from app.gateway.transport.errors import INVALID_TOOL_INPUT, MCPError


class GetProductsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(
        min_length=1, max_length=100,
        description="Tenant slug. Must match the authenticated principal's tenant.",
    )
    category: str | None = Field(default=None, max_length=100)
    max_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class AgentProductView(BaseModel):
    """Exactly what buyer agents see — redacted of any internal fields."""
    sku: str
    name: str
    description: str
    category: str
    base_price: float
    currency: str
    unit: str


class GetProductsOutput(BaseModel):
    products: list[AgentProductView]
    count: int


class GetProductsTool(Tool[GetProductsInput, GetProductsOutput]):
    name = "get_products"
    title = "List agent-accessible products"
    description = (
        "List the seller's product catalog that has been explicitly opened to "
        "buyer-side AI agents. Supports filtering by category, currency, and "
        "maximum base price."
    )
    Input = GetProductsInput
    Output = GetProductsOutput
    required_scope = "mcp:call"

    async def execute(self, inp: GetProductsInput, ctx: ToolContext) -> GetProductsOutput:
        if inp.tenant_id != ctx.tenant_id:
            raise MCPError(
                INVALID_TOOL_INPUT,
                "tenant_id in request does not match authenticated tenant",
                data={"authenticated_tenant": ctx.tenant_id, "requested_tenant": inp.tenant_id},
            )

        products: list[dict[str, Any]] = await list_products_for_agent(
            tenant_slug=inp.tenant_id,
            principal_id=ctx.principal_id,
            filters=AgentProductFilters(
                category=inp.category,
                max_price=inp.max_price,
                currency=inp.currency,
                limit=inp.limit,
            ),
        )

        return GetProductsOutput(
            products=[AgentProductView.model_validate(p) for p in products],
            count=len(products),
        )
