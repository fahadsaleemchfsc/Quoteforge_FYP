"""
MCP tool: request_quote

Buyer agent supplies tenant_id, buyer context, and a list of `{sku, quantity}`
entries. The seller's catalog is authoritative for unit_price — buyer agents
cannot propose their own prices. SKUs must be agent_exposed=True for the
tenant; otherwise the call fails before any persistence side-effects.

Output is a signed offer payload (HMAC-SHA256) that accept_offer will verify
without re-hitting the DB for the pricing check.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.gateway.adapters.quote_adapter import (
    GuardrailBlockError,
    QuoteLineRequest,
    QuoteRequestInput,
    UnknownSkusError,
    build_quote_draft,
)
from app.gateway.tools.base import Tool, ToolContext
from app.gateway.transport.errors import INVALID_TOOL_INPUT, MCPError

# Gateway guardrail error codes — see transport/errors.py for the range.
GUARDRAIL_BLOCK_AT_QUOTE = -32009


class QuoteLineSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=1_000_000)


class BuyerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_name: str = Field(min_length=1, max_length=200)
    deal_name: str = Field(default="", max_length=200)
    # Format constraint only — the Guardrail Engine's RegionCheck is the
    # authoritative allowlist. Keeping a second list here would create drift.
    region: str = Field(
        default="US", min_length=2, max_length=10,
        pattern=r"^[A-Za-z]{2,10}$",
    )
    contact_email: EmailStr | None = None


class RequestQuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(
        min_length=1, max_length=100,
        description="Tenant slug. Must match the authenticated principal's tenant.",
    )
    buyer_context: BuyerContext
    line_items: list[QuoteLineSchema] = Field(min_length=1, max_length=50)


class PricingBlock(BaseModel):
    subtotal: float
    discount: float
    discount_details: list[dict[str, Any]]
    tax: float
    tax_details: list[dict[str, Any]]
    total: float
    total_cents: int
    currency: str


class OfferPayload(BaseModel):
    offer_id: str
    doc_id: str
    tenant_id: str
    issued_at: str
    valid_until: str
    client_name: str
    deal_name: str
    region: str
    contact_email: str | None
    line_items: list[dict[str, Any]]
    pricing: PricingBlock


class RequestQuoteOutput(BaseModel):
    offer: OfferPayload
    signature: str = Field(description="Base64url HMAC-SHA256 over the canonical offer.")
    signature_algorithm: Literal["HS256"] = "HS256"
    total_cents: int = Field(description="Convenience mirror of offer.pricing.total_cents.")
    requires_approval: bool = Field(
        description=(
            "Preview: whether accept_offer on this offer would route to the "
            "human approval queue given the seller's current policy. Policy "
            "can change between request_quote and accept_offer, so accept_offer "
            "is still the source of truth."
        ),
    )
    approval_threshold_cents: int = Field(
        description="The seller's current auto-commit ceiling, in cents.",
    )
    negotiation_mode: str = Field(
        description="Which pricing path produced this offer: 'ai_first' or 'deterministic'.",
    )
    negotiation_attempts: int = Field(
        default=0,
        description="Number of negotiation attempts made (0 for deterministic mode).",
    )
    fell_back_to_deterministic: bool = Field(
        default=False,
        description="True if ai_first exhausted retries and used catalog base prices.",
    )
    model_backend: str | None = Field(
        default=None,
        description="Which backend produced the proposal when ai_first was active.",
    )


class RequestQuoteTool(Tool[RequestQuoteInput, RequestQuoteOutput]):
    name = "request_quote"
    title = "Request a quote"
    description = (
        "Request a priced quote for one or more SKUs. Returns a signed offer "
        "payload valid for 30 days. SKUs must be in the seller's "
        "agent-exposed catalog; unit prices are authoritative from the seller."
    )
    Input = RequestQuoteInput
    Output = RequestQuoteOutput
    required_scope = "mcp:call"

    async def execute(self, inp: RequestQuoteInput, ctx: ToolContext) -> RequestQuoteOutput:
        if inp.tenant_id != ctx.tenant_id:
            raise MCPError(
                INVALID_TOOL_INPUT,
                "tenant_id in request does not match authenticated tenant",
                data={"authenticated_tenant": ctx.tenant_id, "requested_tenant": inp.tenant_id},
            )

        adapter_input = QuoteRequestInput(
            tenant_id=inp.tenant_id,
            principal_id=ctx.principal_id,
            client_name=inp.buyer_context.client_name,
            deal_name=inp.buyer_context.deal_name,
            region=inp.buyer_context.region,
            contact_email=str(inp.buyer_context.contact_email) if inp.buyer_context.contact_email else "",
            line_items=tuple(
                QuoteLineRequest(sku=li.sku, quantity=li.quantity)
                for li in inp.line_items
            ),
        )

        try:
            result = await build_quote_draft(adapter_input)
        except UnknownSkusError as e:
            raise MCPError(
                INVALID_TOOL_INPUT,
                "one or more skus are not available for agent purchase",
                data={"unavailable_skus": e.skus},
            ) from e
        except GuardrailBlockError as e:
            external = e.result.external_payload()
            raise MCPError(
                GUARDRAIL_BLOCK_AT_QUOTE,
                "offer cannot be constructed within seller policies",
                data={
                    "reason": external.get("reason"),
                    "suggested_adjustment": external.get("suggested_adjustment"),
                },
            ) from e
        except ValueError as e:
            raise MCPError(INVALID_TOOL_INPUT, str(e)) from e

        return RequestQuoteOutput.model_validate(result)
