"""
MCP server core — tool registry and JSON-RPC method dispatcher.

Transport-agnostic on purpose: `MCPServer.handle(request, ctx)` takes a parsed
JsonRpcRequest and a per-call context (principal, tenant, etc.) and returns
either a JsonRpcResponse or None (for notifications). The HTTP transport layer
is a thin adapter over this.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from app.gateway.schemas.mcp import (
    PROTOCOL_VERSION,
    CallToolParams,
    CallToolResult,
    InitializeParams,
    InitializeResult,
    JsonRpcId,
    JsonRpcRequest,
    JsonRpcResponse,
    ListToolsResult,
    ServerCapabilities,
    ServerInfo,
    ToolDefinition,
)
from app.gateway.tools.base import Tool, ToolContext
from app.gateway.transport.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_TOOL_INPUT,
    METHOD_NOT_FOUND,
    TOOL_NOT_FOUND,
    MCPError,
    error_response,
)

logger = logging.getLogger(__name__)

SERVER_NAME = "quoteforge-agent-gateway"
SERVER_VERSION = "0.1.0"
SERVER_TITLE = "QuoteForge Agent Gateway"


@dataclass
class CallContext:
    """Per-request context passed into every tool invocation."""

    tenant_id: str
    principal_id: str           # OAuth subject — the MCP client identity
    scopes: frozenset[str]
    request_id: JsonRpcId


MethodHandler = Callable[[JsonRpcRequest, CallContext], Awaitable["JsonRpcResponse | None"]]


class MCPServer:
    """Stateless dispatcher. One instance is shared across requests."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._methods: dict[str, MethodHandler] = {
            "initialize": self._on_initialize,
            "notifications/initialized": self._on_initialized_notification,
            "ping": self._on_ping,
            "tools/list": self._on_tools_list,
            "tools/call": self._on_tools_call,
        }

    # ---------- registration ------------------------------------------------

    def register_tool(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        logger.info("mcp: registered tool %s", tool.name)

    def registered_tools(self) -> list[str]:
        return list(self._tools)

    # ---------- entrypoint --------------------------------------------------

    async def handle(self, request: JsonRpcRequest, ctx: CallContext) -> JsonRpcResponse | None:
        """Dispatch a single parsed request. Returns None for notifications."""
        handler = self._methods.get(request.method)
        if handler is None:
            if request.is_notification:
                return None
            return error_response(request.id, METHOD_NOT_FOUND, f"method not found: {request.method}")

        try:
            return await handler(request, ctx)
        except MCPError as e:
            if request.is_notification:
                logger.warning("mcp: notification raised MCPError code=%s: %s", e.code, e.message)
                return None
            return error_response(request.id, e.code, e.message, e.data)
        except ValidationError as e:
            if request.is_notification:
                return None
            return error_response(request.id, INVALID_PARAMS, "invalid params", data=e.errors())
        except Exception as e:  # noqa: BLE001 — last-resort safety net
            logger.exception("mcp: unhandled error in method %s", request.method)
            if request.is_notification:
                return None
            return error_response(request.id, INTERNAL_ERROR, "internal error", data=str(e))

    # ---------- method handlers --------------------------------------------

    async def _on_initialize(self, request: JsonRpcRequest, ctx: CallContext) -> JsonRpcResponse:
        params = InitializeParams.model_validate(request.params or {})
        # Protocol negotiation: if client requested a version we don't know,
        # we reply with ours; client must then disconnect or accept.
        result = InitializeResult(
            protocolVersion=PROTOCOL_VERSION,
            capabilities=ServerCapabilities(tools={"listChanged": False}),
            serverInfo=ServerInfo(name=SERVER_NAME, version=SERVER_VERSION, title=SERVER_TITLE),
            instructions=(
                "QuoteForge Agent Gateway. Call tools/list to discover available tools. "
                "All tool calls are subject to deterministic guardrails and per-tenant rate limits."
            ),
        )
        logger.info(
            "mcp: initialize client=%s/%s requested=%s served=%s",
            params.clientInfo.name, params.clientInfo.version,
            params.protocolVersion, PROTOCOL_VERSION,
        )
        return JsonRpcResponse(id=request.id, result=result.model_dump(exclude_none=True))

    async def _on_initialized_notification(self, request: JsonRpcRequest, ctx: CallContext) -> None:
        # Per spec, the client sends this after processing initialize. No reply.
        return None

    async def _on_ping(self, request: JsonRpcRequest, ctx: CallContext) -> JsonRpcResponse:
        return JsonRpcResponse(id=request.id, result={})

    async def _on_tools_list(self, request: JsonRpcRequest, ctx: CallContext) -> JsonRpcResponse:
        tool_defs: list[ToolDefinition] = [t.definition() for t in self._tools.values()]
        result = ListToolsResult(tools=tool_defs)
        return JsonRpcResponse(id=request.id, result=result.model_dump(exclude_none=True))

    async def _on_tools_call(self, request: JsonRpcRequest, ctx: CallContext) -> JsonRpcResponse:
        params = CallToolParams.model_validate(request.params or {})
        tool = self._tools.get(params.name)
        if tool is None:
            raise MCPError(TOOL_NOT_FOUND, f"tool not found: {params.name}")

        tool_ctx = ToolContext(
            tenant_id=ctx.tenant_id,
            principal_id=ctx.principal_id,
            scopes=ctx.scopes,
        )

        try:
            structured = await tool.run(params.arguments, tool_ctx)
        except MCPError:
            raise
        except ValidationError as e:
            raise MCPError(INVALID_TOOL_INPUT, "invalid tool arguments", data=e.errors()) from e

        result = CallToolResult(
            content=[{"type": "text", "text": json.dumps(structured, default=str)}],
            structuredContent=structured,
            isError=False,
        )
        return JsonRpcResponse(id=request.id, result=result.model_dump(exclude_none=True))


# Module-level singleton wired up at app startup in main.py
_server: MCPServer | None = None


def get_server() -> MCPServer:
    global _server
    if _server is None:
        _server = MCPServer()
    return _server
