"""
PharmaWatch MCP server, stdio launcher (the path Claude Desktop and other MCP clients are configured with).
The server itself lives in the pharmawatch_mcp package.

    python mcp_server.py
    npx @modelcontextprotocol/inspector python mcp_server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # clients start servers from any directory

from pharmawatch_mcp import main, mcp  # noqa: E402,F401

if __name__ == "__main__":
    main()
