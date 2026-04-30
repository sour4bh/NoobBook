"""Anthropic Messages schema compilation for Pydantic-owned contracts."""

from __future__ import annotations

from app.agents.runtime.tool import LocalToolSpec, McpProxyToolSpec


def tool_schema(tool: LocalToolSpec | McpProxyToolSpec) -> dict[str, object]:
    """Compile a local runtime tool into Anthropic's tool definition shape."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_model.model_json_schema(by_alias=True),
    }
