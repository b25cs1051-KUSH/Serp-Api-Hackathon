"""JSON Schema clean-up for MCP clients that don't resolve $ref / $defs."""

import copy
from typing import Optional

from mcp.server.mcpserver import MCPServer


def inline_refs(schema: Optional[dict]) -> Optional[dict]:
    """Replace "$ref": "#/$defs/X" with the definition itself and drop $defs. Some MCP clients don't resolve
    $defs and would show list items as {} (a prescription item without its name / tablets fields)."""
    if not schema or "$defs" not in schema:
        return schema
    defs = schema["$defs"]

    def walk(node, seen=()):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.split("/")[-1]
                if name in seen:  # a recursive model: stop with a plain object instead of looping
                    return {"type": "object"}
                merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
                return walk(merged, seen + (name,))
            return {k: walk(v, seen) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v, seen) for v in node]
        return node

    return walk(schema)


def inline_tool_schemas(server: MCPServer) -> None:
    """Inline every registered tool's input and output schema (call once, after the tools are registered)."""
    for tool in server._tool_manager.list_tools():
        tool.parameters = inline_refs(tool.parameters)
        if tool.fn_metadata.output_schema is not None:
            tool.fn_metadata.output_schema = inline_refs(tool.fn_metadata.output_schema)
