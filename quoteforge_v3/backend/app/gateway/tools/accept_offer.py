"""
MCP tool: accept_offer

Buyer agent sends back (offer_id, signature) pair from request_quote. We:
  1. Verify the HMAC.
  2. Enforce expiry.
  3. Route per TenantConfig — either queue for human review or commit.
  4. Every outcome (including rejections) writes a Replay Layer entry.

Output is a discriminated union on `status`. Buyer agents that only know how
to handle `accepted` will still branch correctly on `pending_approval` because
`document_id` is absent; agents that don't recognize `status=expired` should
treat it as terminal and re-quote.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel

from app.core.database import async_session
from app.gateway.adapters.offer_adapter import (
    STATUS_POLICY_INVALIDATED,
    InvalidOfferSignatureError,
    OfferExpiredError,
    OfferNotFoundError,
    OfferRejectedError,
    PolicyInvalidatedError,
    commit_offer,
    ensure_offer_not_expired,
    queue_for_approval,
    re_evaluate_against_policy,
    verify_and_load_offer,
)
from app.gateway.adapters.quote_adapter import load_approval_policy
from app.gateway.tools.base import Tool, ToolContext
from app.gateway.transport.errors import (
    INTERNAL_ERROR,
    INVALID_TOOL_INPUT,
    MCPError,
)

# Gateway-specific error codes — extend the -3202x block from transport/errors.py.
OFFER_INVALID_SIGNATURE = -32021
OFFER_NOT_FOUND = -32022
OFFER_EXPIRED = -32023
OFFER_REJECTED_BY_SELLER = -32024
OFFER_POLICY_INVALIDATED = -32010


class AcceptOfferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=100)
    offer_id: str = Field(min_length=1, max_length=64)
    signature: str = Field(min_length=1, max_length=256)
    buyer_reference: str | None = Field(
        default=None, max_length=200,
        description="Buyer's internal reference (PO number etc.), stored as metadata.",
    )


class AcceptedResult(BaseModel):
    status: Literal["accepted"] = "accepted"
    document_id: str
    offer_id: str
    total_cents: int
    currency: str
    committed_at: str
    idempotent_replay: bool = Field(
        default=False,
        description="True when this was a repeat accept of an already-committed offer.",
    )


class PendingApprovalResult(BaseModel):
    status: Literal["pending_approval"] = "pending_approval"
    approval_id: str
    offer_id: str
    total_cents: int
    expires_at: str
    idempotent_replay: bool = False


class AcceptOfferOutput(RootModel[Annotated[
    Union[AcceptedResult, PendingApprovalResult],
    Field(discriminator="status"),
]]):
    """Discriminated union output. RootModel.model_dump unwraps the root so
    the wire shape is the inner AcceptedResult / PendingApprovalResult directly.
    The advertised JSON schema is likewise the union schema."""


class AcceptOfferTool(Tool[AcceptOfferInput, AcceptOfferOutput]):
    name = "accept_offer"
    title = "Accept a signed offer"
    description = (
        "Accept a previously-issued offer by returning its offer_id + "
        "signature. The server verifies the signature, checks expiry, and "
        "either commits the deal or routes it to human approval per the "
        "seller's policy. Idempotent: re-accepting the same offer_id returns "
        "the original outcome."
    )
    Input = AcceptOfferInput
    Output = AcceptOfferOutput
    required_scope = "mcp:call"

    async def execute(self, inp: AcceptOfferInput, ctx: ToolContext) -> AcceptOfferOutput:
        if inp.tenant_id != ctx.tenant_id:
            raise MCPError(
                INVALID_TOOL_INPUT,
                "tenant_id in request does not match authenticated tenant",
                data={"authenticated_tenant": ctx.tenant_id, "requested_tenant": inp.tenant_id},
            )

        async with async_session() as db:
            try:
                fetched = await verify_and_load_offer(
                    db,
                    tenant_slug=inp.tenant_id,
                    offer_id=inp.offer_id,
                    signature=inp.signature,
                )
            except OfferNotFoundError:
                raise MCPError(OFFER_NOT_FOUND, "offer not found", data={"offer_id": inp.offer_id})
            except InvalidOfferSignatureError:
                raise MCPError(OFFER_INVALID_SIGNATURE, "invalid offer signature", data={"offer_id": inp.offer_id})

            # Reload policy at accept time — it may have tightened since the
            # quote was issued (the preview in request_quote is advisory).
            policy = await load_approval_policy(db, inp.tenant_id)
            if policy is None:
                # Extremely unlikely — tenant was deleted between quote and accept.
                raise MCPError(INTERNAL_ERROR, "tenant config unavailable")

            # Fast path for already-decided offers (idempotency).
            doc_status = fetched.document_log.status
            if doc_status == "committed":
                # Re-accept: return the original receipt.
                try:
                    result = await commit_offer(
                        db, fetched=fetched, tenant_id_uuid=policy.tenant_id,
                        buyer_agent_id=ctx.principal_id, source="agent_gateway",
                        buyer_reference=inp.buyer_reference,
                    )
                except OfferRejectedError:
                    raise MCPError(OFFER_REJECTED_BY_SELLER, "offer was rejected by the seller",
                                   data={"offer_id": inp.offer_id})
                await db.commit()
                return AcceptOfferOutput(AcceptedResult(
                    document_id=result.document_id,
                    offer_id=result.offer_id,
                    total_cents=result.total_cents,
                    currency=result.currency,
                    committed_at=result.committed_at.isoformat(),
                    idempotent_replay=True,
                ))

            if doc_status == "rejected":
                raise MCPError(OFFER_REJECTED_BY_SELLER, "offer was rejected by the seller",
                               data={"offer_id": inp.offer_id})

            # Only enforce expiry on paths that would actually create / mutate.
            try:
                ensure_offer_not_expired(fetched)
            except OfferExpiredError:
                raise MCPError(OFFER_EXPIRED, "offer expired", data={"offer_id": inp.offer_id})

            # Defense-in-depth: re-run guardrails. Policy or product floors may
            # have tightened between quote and accept.
            engine_result = await re_evaluate_against_policy(
                db, fetched=fetched, principal_id=ctx.principal_id,
            )
            if engine_result.verdict == "block":
                fetched.document_log.status = STATUS_POLICY_INVALIDATED
                await db.commit()
                external = engine_result.external_payload()
                raise MCPError(
                    OFFER_POLICY_INVALIDATED,
                    "offer no longer valid under current policy",
                    data={
                        "offer_id": inp.offer_id,
                        "reason": external.get("reason"),
                        "suggested_adjustment": external.get("suggested_adjustment"),
                    },
                )

            total_cents = int(fetched.offer_payload["pricing"]["total_cents"])
            # Either the engine flagged review, or the tenant has auto-commit
            # turned off (kill-switch). Both route to the approval queue.
            requires_approval = (
                engine_result.verdict == "review" or not policy.auto_commit_enabled
            )
            if requires_approval:
                queued = await queue_for_approval(
                    db,
                    fetched=fetched,
                    tenant_id_uuid=policy.tenant_id,
                    buyer_agent_id=ctx.principal_id,
                )
                await db.commit()
                return AcceptOfferOutput(PendingApprovalResult(
                    approval_id=queued.approval_id,
                    offer_id=queued.offer_id,
                    total_cents=total_cents,
                    expires_at=queued.expires_at.isoformat(),
                    idempotent_replay=queued.was_already_queued,
                ))

            try:
                result = await commit_offer(
                    db, fetched=fetched, tenant_id_uuid=policy.tenant_id,
                    buyer_agent_id=ctx.principal_id, source="agent_gateway",
                    buyer_reference=inp.buyer_reference,
                )
            except OfferRejectedError:
                raise MCPError(OFFER_REJECTED_BY_SELLER, "offer was rejected by the seller",
                               data={"offer_id": inp.offer_id})
            await db.commit()
            return AcceptOfferOutput(AcceptedResult(
                document_id=result.document_id,
                offer_id=result.offer_id,
                total_cents=result.total_cents,
                currency=result.currency,
                committed_at=result.committed_at.isoformat(),
                idempotent_replay=result.was_already_committed,
            ))
