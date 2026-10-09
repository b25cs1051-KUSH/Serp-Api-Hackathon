"""
Streamable HTTP transport: the public connector. attach(app) adds POST/GET /mcp to the existing FastAPI
app, so the hosted API serves the website and MCP clients from one process (one Render service, one cache,
one credit budget, one link registry for get_buy_link).

Stateless mode: every request is independent, so a restart or a second instance never breaks a client.

    MCP_ALLOWED_HOSTS=pharmawatch-api-7wm1.onrender.com   Host headers accepted (DNS-rebinding protection);
                                                          unset = no Host check (local development)
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from .app import mcp

PATH = "/mcp"


def _security() -> TransportSecuritySettings:
    hosts = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                     allowed_origins=[f"https://{h}" for h in hosts])


def attach(app: FastAPI) -> None:
    """Serve MCP at /mcp on `app` and run the MCP session manager inside the app's lifespan."""
    sub = mcp.streamable_http_app(streamable_http_path=PATH, stateless_http=True,
                                  transport_security=_security(), host="0.0.0.0")
    app.router.routes.extend(sub.routes)

    outer = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(a):
        async with outer(a), mcp.session_manager.run():
            yield

    app.router.lifespan_context = lifespan
