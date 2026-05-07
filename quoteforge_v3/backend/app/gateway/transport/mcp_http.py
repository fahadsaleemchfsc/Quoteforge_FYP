"""
MCP Streamable HTTP transport (spec revision 2026-06-18).

One endpoint: POST/GET/DELETE /mcp.

 * POST  /mcp        — client sends a single JSON-RPC request or a JSON-RPC
                        batch. We respond with `application/json` for the
                        synchronous case. If a handler ever needs to stream
                        (progress notifications, partial results), we can
                        upgrade to `text/event-stream` from the same endpoint.
 * GET   /mcp        — opens a server-initiated SSE stream for out-of-band
                        notifications. We return 405 for now since our tools
                        are all request/response. Handlers are in place so
                        enabling streaming later is a one-line change.
 * DELETE /mcp       — terminate the session identified by Mcp-Session-Id.

Session model:
  We run stateless: every call must carry a valid OAuth bearer that identifies
  tenant + principal. `Mcp-Session-Id` is accepted and echoed for clients that
  require it, but we do not rely on server-side session state — this is what
  makes horizontal scaling trivial.

Reference: https://spec.modelcontextprotocol.io/specification/2026-06-18/basic/transports
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError

from app.gateway.auth.deps import require_mcp_principal, MCPPrincipal
from app.gateway.ratelimit.token_bucket import enforce_rate_limit
from app.gateway.schemas.mcp import JsonRpcRequest, JsonRpcResponse
from app.gateway.server import CallContext, get_server
from app.gateway.transport.errors import (
    INVALID_REQUEST,
    PARSE_ERROR,
    error_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

_SESSION_HEADER = "Mcp-Session-Id"
_PROTOCOL_HEADER = "MCP-Protocol-Version"


def _parse_body(raw: bytes) -> tuple[list[JsonRpcRequest], bool] | JsonRpcResponse:
    """Parse a request body into one-or-more JSON-RPC requests.

    Returns (requests, is_batch) on success, or a JsonRpcResponse carrying a
    parse/validation error on failure.
    """
    if not raw:
        return error_response(None, INVALID_REQUEST, "empty request body")

    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as e:
        return error_response(None, PARSE_ERROR, f"invalid JSON: {e.msg}")

    is_batch = isinstance(payload, list)
    items = payload if is_batch else [payload]
    if is_batch and not items:
        return error_response(None, INVALID_REQUEST, "empty batch")

    parsed: list[JsonRpcRequest] = []
    for item in items:
        try:
            parsed.append(JsonRpcRequest.model_validate(item))
        except ValidationError as e:
            return error_response(None, INVALID_REQUEST, "invalid JSON-RPC request", data=e.errors())
    return parsed, is_batch


def _response_payload(resp: JsonRpcResponse) -> dict[str, Any]:
    return resp.model_dump(mode="json", exclude_none=True)


@router.post("")
async def mcp_post(
    request: Request,
    principal: MCPPrincipal = Depends(require_mcp_principal),
    mcp_session_id: str | None = Header(default=None, alias=_SESSION_HEADER),
    mcp_protocol_version: str | None = Header(default=None, alias=_PROTOCOL_HEADER),
) -> Response:
    await enforce_rate_limit(principal)

    raw = await request.body()
    parsed = _parse_body(raw)
    if isinstance(parsed, JsonRpcResponse):
        return JSONResponse(_response_payload(parsed), status_code=400)

    requests, is_batch = parsed
    server = get_server()

    responses: list[JsonRpcResponse] = []
    for rpc_req in requests:
        ctx = CallContext(
            tenant_id=principal.tenant_id,
            principal_id=principal.subject,
            scopes=principal.scopes,
            request_id=rpc_req.id,
        )
        resp = await server.handle(rpc_req, ctx)
        if resp is not None:
            responses.append(resp)

    # Echo/assign session id so stateful clients are happy.
    session_id = mcp_session_id or uuid.uuid4().hex
    headers = {_SESSION_HEADER: session_id, _PROTOCOL_HEADER: "2026-06-18"}

    # Pure-notification batch (no responses) — per JSON-RPC 2.0, reply 204.
    if not responses:
        return Response(status_code=204, headers=headers)

    if is_batch:
        body: Any = [_response_payload(r) for r in responses]
    else:
        body = _response_payload(responses[0])

    return JSONResponse(body, headers=headers)


@router.get("")
async def mcp_get(
    principal: MCPPrincipal = Depends(require_mcp_principal),
) -> Response:
    """Server-initiated SSE stream. Not used yet — 405 signals that cleanly."""
    return PlainTextResponse(
        "server-initiated streaming not enabled",
        status_code=405,
        headers={"Allow": "POST, DELETE"},
    )


@router.delete("")
async def mcp_delete(
    principal: MCPPrincipal = Depends(require_mcp_principal),
    mcp_session_id: str | None = Header(default=None, alias=_SESSION_HEADER),
) -> Response:
    """Session termination. Stateless server — always 204."""
    logger.info(
        "mcp: session terminated principal=%s tenant=%s session=%s",
        principal.subject, principal.tenant_id, mcp_session_id,
    )
    return Response(status_code=204)
