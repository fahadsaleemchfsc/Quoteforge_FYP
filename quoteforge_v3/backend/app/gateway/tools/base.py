"""
Tool base class.

A Tool is a pair of Pydantic models (input/output) plus an async `execute()`.
The base class does argument validation so every tool handler gets a parsed,
typed input model rather than a raw dict.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.gateway.schemas.mcp import ToolDefinition

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


@dataclass(frozen=True)
class ToolContext:
    tenant_id: str
    principal_id: str
    scopes: frozenset[str]


class Tool(ABC, Generic[I, O]):
    """Base class for MCP tools.

    Subclasses set class-level `name`, `title`, `description`, and the two
    Pydantic model types `Input` / `Output`, then implement `execute`.
    """

    name: str
    title: str
    description: str
    Input: type[I]
    Output: type[O]
    required_scope: str | None = None

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            title=self.title,
            description=self.description,
            inputSchema=self.Input.model_json_schema(),
            outputSchema=self.Output.model_json_schema(),
        )

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Validate input, call execute, serialize output."""
        parsed = self.Input.model_validate(arguments)
        result = await self.execute(parsed, ctx)
        return result.model_dump(mode="json", exclude_none=True)

    @abstractmethod
    async def execute(self, inp: I, ctx: ToolContext) -> O:
        ...
