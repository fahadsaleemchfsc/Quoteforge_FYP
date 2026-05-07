"""
Aggregates all gateway sub-routers so main.py mounts a single entry point.

Mount path: the gateway lives at the server root (NOT under /api) so that
well-known URIs and OAuth endpoints sit where MCP clients expect them:
    /mcp
    /.well-known/ucp/manifest.json   (added in next step)
    /.well-known/oauth-authorization-server  (added in next step)
    /oauth/token                     (added in next step)
"""
from __future__ import annotations

from fastapi import APIRouter

from app.gateway.transport.mcp_http import router as mcp_router

router = APIRouter()
router.include_router(mcp_router)


def register_builtin_tools() -> None:
    """Called at startup to register every Tool subclass we ship.

    Tools are appended here as each one is implemented. Keeping registration
    centralized makes it trivial to see the server's surface area.
    """
    from app.gateway.server import get_server
    from app.gateway.tools.accept_offer import AcceptOfferTool
    from app.gateway.tools.get_products import GetProductsTool
    from app.gateway.tools.request_quote import RequestQuoteTool

    server = get_server()
    server.register_tool(GetProductsTool())
    server.register_tool(RequestQuoteTool())
    server.register_tool(AcceptOfferTool())
