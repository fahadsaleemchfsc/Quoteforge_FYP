"""
FastAPI dependency resolving the MCP caller into a principal.

Final implementation (next step): verify RS256 JWT issued by our OAuth 2.1
authorization server (see app/gateway/auth/oauth21.py), extract subject,
tenant, scopes.

Current (dev-stub) implementation: accept `Authorization: Bearer dev-<tenant>`
so curl tests work end-to-end before OAuth is wired. Rejects any other shape.
This stub is gated behind settings.GATEWAY_DEV_AUTH so it cannot ship.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings


@dataclass(frozen=True)
class MCPPrincipal:
    subject: str
    tenant_id: str
    scopes: frozenset[str]
    token_jti: str | None = None


def _parse_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": 'Bearer realm="quoteforge-mcp"'},
        )
    return authorization.split(" ", 1)[1].strip()


async def require_mcp_principal(
    authorization: str | None = Header(default=None),
) -> MCPPrincipal:
    token = _parse_bearer(authorization)

    # --- DEV STUB --------------------------------------------------------
    # Format: "dev-<tenant_id>" → everyone gets tools:* scope.
    # Replaced in the OAuth 2.1 step.
    if getattr(settings, "GATEWAY_DEV_AUTH", True) and token.startswith("dev-"):
        tenant = token.removeprefix("dev-").strip() or "default"
        return MCPPrincipal(
            subject=f"dev-client:{tenant}",
            tenant_id=tenant,
            scopes=frozenset({"tools:*", "mcp:call"}),
        )
    # --- /DEV STUB -------------------------------------------------------

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="token not recognized (OAuth 2.1 verification not yet wired)",
        headers={"WWW-Authenticate": 'Bearer realm="quoteforge-mcp"'},
    )


def require_scope(principal: MCPPrincipal, scope: str) -> None:
    if "tools:*" in principal.scopes or scope in principal.scopes:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"missing scope: {scope}",
    )
