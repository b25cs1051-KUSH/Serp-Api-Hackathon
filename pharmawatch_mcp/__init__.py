"""
PharmaWatch as an MCP server.

    app.py      the MCPServer instance and the instructions the model reads
    models.py   typed inputs and outputs (each output model is a tool's outputSchema)
    convert.py  the API's result dicts → output models
    render.py   output models → compact Markdown
    tools.py    search_medicine, plan_prescription, get_buy_link, cache_lab, cache_stats
    prompts.py  compare_medicine, plan_my_prescription
    schemas.py  $ref inlining for clients that don't resolve $defs
    stdio.py    local transport (Claude Desktop, Cursor, MCP Inspector)
    remote.py   public transport: Streamable HTTP at /mcp on the hosted API

Run locally:  python mcp_server.py   or   python -m pharmawatch_mcp
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # MCP clients start servers from any directory

from . import prompts, tools  # noqa: E402,F401  (registers the tools and prompts on the server)
from .app import mcp  # noqa: E402
from .schemas import inline_tool_schemas  # noqa: E402
from .stdio import main  # noqa: E402

inline_tool_schemas(mcp)

__all__ = ["mcp", "main"]
