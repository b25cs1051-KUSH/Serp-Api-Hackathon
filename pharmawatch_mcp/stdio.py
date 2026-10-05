"""stdio transport: how Claude Desktop, Cursor and MCP Inspector start a local server."""

import io
import os
import sys

import anyio
from mcp.server.stdio import stdio_server

from .app import mcp


async def _serve(wire_fd: int) -> None:
    wire = anyio.wrap_file(io.TextIOWrapper(os.fdopen(wire_fd, "wb"), encoding="utf-8"))
    async with stdio_server(stdout=wire) as (read_stream, write_stream):
        # Same as MCPServer.run_stdio_async, with an explicit stdout (there is no public hook for one).
        await mcp._lowlevel_server.run(read_stream, write_stream, mcp._lowlevel_server.create_initialization_options())


def main() -> None:
    """Serve MCP over stdio. The protocol gets a private copy of stdout; fd 1 and sys.stdout point at stderr
    for the whole run, so the cache's console prints ("Redis connected") and library warnings can never
    land on the wire and break the client's parser (the SDK's own diversion is undone at shutdown, when
    Python flushes buffered prints)."""
    sys.stdout.flush()
    wire_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    anyio.run(_serve, wire_fd)
