"""
MCP protocol schemas — JSON-RPC 2.0 envelope + MCP 2026-06-18 method payloads.

Spec: https://spec.modelcontextprotocol.io/specification/2026-06-18/

Only the subset of methods we need for the Agent Gateway is modeled here:
  - initialize / initialized
  - tools/list
  - tools/call
  - ping
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# MCP protocol revision we implement
PROTOCOL_VERSION: Literal["2026-06-18"] = "2026-06-18"

# JSON-RPC 2.0 id is string | number | null (null is allowed for notifications
# only; we validate that separately on the handler).
JsonRpcId = str | int | None


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope
# ---------------------------------------------------------------------------

class JsonRpcRequest(BaseModel):
    """Incoming JSON-RPC request (or notification if id is absent)."""
    model_config = ConfigDict(extra="allow")

    jsonrpc: Literal["2.0"]
    method: str
    params: dict[str, Any] | list[Any] | None = None
    id: JsonRpcId = None

    @property
    def is_notification(self) -> bool:
        return self.id is None


class JsonRpcErrorPayload(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    """Outgoing JSON-RPC response. Exactly one of `result` or `error` is set."""
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: JsonRpcId
    result: Any | None = None
    error: JsonRpcErrorPayload | None = None


# ---------------------------------------------------------------------------
# MCP — initialize
# ---------------------------------------------------------------------------

class ClientCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")
    roots: dict[str, Any] | None = None
    sampling: dict[str, Any] | None = None
    elicitation: dict[str, Any] | None = None


class ClientInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    version: str
    title: str | None = None


class InitializeParams(BaseModel):
    model_config = ConfigDict(extra="allow")
    protocolVersion: str
    capabilities: ClientCapabilities = Field(default_factory=ClientCapabilities)
    clientInfo: ClientInfo


class ServerCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")
    tools: dict[str, Any] | None = Field(
        default_factory=lambda: {"listChanged": False}
    )
    logging: dict[str, Any] | None = None


class ServerInfo(BaseModel):
    name: str
    version: str
    title: str | None = None


class InitializeResult(BaseModel):
    protocolVersion: str = PROTOCOL_VERSION
    capabilities: ServerCapabilities = Field(default_factory=ServerCapabilities)
    serverInfo: ServerInfo
    instructions: str | None = None


# ---------------------------------------------------------------------------
# MCP — tools/list
# ---------------------------------------------------------------------------

class ToolDefinition(BaseModel):
    """A tool the server advertises. `inputSchema` is a JSON Schema object."""
    model_config = ConfigDict(extra="allow")

    name: str
    title: str | None = None
    description: str
    inputSchema: dict[str, Any]
    outputSchema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None


class ListToolsResult(BaseModel):
    tools: list[ToolDefinition]
    nextCursor: str | None = None


# ---------------------------------------------------------------------------
# MCP — tools/call
# ---------------------------------------------------------------------------

class CallToolParams(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolContentText(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolContentJson(BaseModel):
    """Structured JSON payload carried as text for transports that are strict
    about content types. Clients can rely on `structuredContent` too."""
    type: Literal["text"] = "text"
    text: str  # JSON-encoded


class CallToolResult(BaseModel):
    content: list[dict[str, Any]]
    structuredContent: dict[str, Any] | None = None
    isError: bool = False
