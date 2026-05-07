"""
JSON-RPC 2.0 / MCP error codes + envelope helpers.

JSON-RPC 2.0 reserves -32768..-32000 for protocol errors. MCP reserves a
portion of the application range for protocol-specific errors.
"""
from __future__ import annotations

from typing import Any

from app.gateway.schemas.mcp import (
    JsonRpcErrorPayload,
    JsonRpcId,
    JsonRpcResponse,
)

# --- JSON-RPC 2.0 standard ----------------------------------------------------
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# --- MCP application errors (spec-aligned) -----------------------------------
RESOURCE_NOT_FOUND = -32002
TOOL_NOT_FOUND = -32004
INVALID_TOOL_INPUT = -32005

# --- Gateway-specific (server range -32000..-32099) --------------------------
UNAUTHENTICATED = -32010
FORBIDDEN = -32011
RATE_LIMITED = -32012
TENANT_SCOPE_MISMATCH = -32013
GUARDRAIL_REJECTED = -32020


class MCPError(Exception):
    """Raised inside tool / dispatch code to short-circuit to a JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def error_response(request_id: JsonRpcId, code: int, message: str, data: Any | None = None) -> JsonRpcResponse:
    return JsonRpcResponse(
        id=request_id,
        error=JsonRpcErrorPayload(code=code, message=message, data=data),
    )
