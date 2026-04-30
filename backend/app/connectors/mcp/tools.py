"""
MCP tool catalog and app-owned proxy execution.

The runtime exposes one typed ``call_mcp_tool`` ToolSpec instead of one local
tool per remote MCP schema. This module discovers enabled MCP server tools,
builds the per-user registry shown in chat context, and validates proxy calls
against the external MCP schema at the connector boundary.

Tool namespacing:
MCP tool ids are prefixed with `mcp_{slug}_` to avoid collision with built-in
tools (search_sources, store_memory, etc.) and between multiple MCP servers.
For example, a Freshdesk MCP server's "create_ticket" tool becomes
"mcp_freshdesk_create_ticket".

Lifecycle:
Each tool call spawns a fresh MCP connection (SSE HTTP request or stdio subprocess).
This is intentionally stateless — no persistent connections to manage.
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema

from app.agents.runtime.tool import McpCallInput, McpProxyToolSpec, ToolContext, ToolOutput

logger = logging.getLogger(__name__)

# All MCP tool names start with this prefix
MCP_TOOL_PREFIX = "mcp_"


def _slugify(name: str) -> str:
    """Convert a connection name to a safe slug for tool namespacing."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip())
    return slug.strip("_") or "mcp"


MCP_PROXY_TOOL_NAME = "call_mcp_tool"


def _proxy_handler(value: McpCallInput, context: ToolContext) -> str | ToolOutput:
    registry = context.metadata.get("mcp_registry")
    if not isinstance(registry, dict):
        return ToolOutput(
            content="MCP tool registry is unavailable for this run",
            is_error=True,
        )
    arguments, error = parse_mcp_arguments_json(value.arguments_json)
    if error:
        return ToolOutput(content=error.removeprefix("Error:").strip(), is_error=True)
    result = mcp_tool_service.execute(
        tool_id=value.tool_id,
        arguments=arguments,
        registry=registry,
    )
    if result.startswith("Error:"):
        return ToolOutput(content=result.removeprefix("Error:").strip(), is_error=True)
    return result


def _proxy_spec() -> McpProxyToolSpec:
    return McpProxyToolSpec(
        name=MCP_PROXY_TOOL_NAME,
        description=(
            "Call one enabled MCP integration tool by tool_id. The available "
            "tool_id values and their argument shapes are listed in the MCP "
            "Tools context. Pass the original tool arguments as an arguments_json "
            "JSON object string."
        ),
        handler=_proxy_handler,
        metadata={"registry_name": MCP_PROXY_TOOL_NAME},
    )


class McpToolService:
    """
    Catalog and dispatcher for app-owned MCP proxy calls.

    Chat asks for the single runtime proxy ToolSpec plus a registry of enabled
    remote MCP tools. Tool execution routes through ``execute`` with a registry
    entry so provider adapters never need to understand remote MCP schemas.
    """

    def get_available_tools(self, user_id: str) -> Tuple[List[McpProxyToolSpec], Dict[str, Dict[str, Any]]]:
        """
        Get all MCP tools available for chat.

        Loads cached tools from all tools-enabled connections accessible to the
        user. Returns the single app-owned proxy ToolSpec plus a registry
        mapping tool ids back to connection/tool/schema metadata.

        Args:
            user_id: The requesting user's ID

        Returns:
            Tuple of:
            - The single app-owned MCP proxy tool, when at least one MCP tool exists
            - Registry dict: {tool_id: connection/tool/schema metadata}
        """
        from app.connectors.mcp.store import mcp_connection_service

        connections = mcp_connection_service.get_tool_enabled_connections(user_id=user_id)

        if not connections:
            return [], {}

        registry: Dict[str, Dict[str, Any]] = {}

        for conn in connections:
            cached_tools = conn.get("cached_tools")
            if not cached_tools or not isinstance(cached_tools, list):
                continue

            connection_id = conn.get("id", "")
            connection_name = conn.get("name", "MCP")
            slug = _slugify(connection_name)

            for tool_def in cached_tools:
                original_name = tool_def.get("name", "")
                if not original_name:
                    continue

                # Namespace the tool name to avoid collisions
                namespaced = f"{MCP_TOOL_PREFIX}{slug}_{original_name}"

                description = tool_def.get("description", "")
                registry[namespaced] = {
                    "connection_id": connection_id,
                    "connection_name": connection_name,
                    "tool_name": original_name,
                    "description": description,
                    "input_schema": tool_def.get(
                        "input_schema",
                        {"type": "object", "properties": {}},
                    ),
                }

        if not registry:
            return [], {}
        return [_proxy_spec()], registry

    def get_tool_catalog(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Return enabled MCP tool metadata keyed by model-visible tool_id."""
        _, registry = self.get_available_tools(user_id=user_id)
        return registry

    def can_handle(self, tool_name: str) -> bool:
        """Check if a tool name is the app-owned MCP proxy."""
        return tool_name == MCP_PROXY_TOOL_NAME

    def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        registry: Dict[str, Dict[str, Any]],
    ) -> str:
        """
        Execute an MCP tool call and return the result text.

        Educational Note: Looks up the connection and original tool name from
        the registry, loads the connection's secrets, then calls mcp_client.call_tool()
        which spawns a fresh connection to the MCP server.

        Args:
            tool_id: The namespaced MCP tool id (e.g., mcp_freshdesk_create_ticket)
            arguments: Arguments for the original MCP server tool
            registry: The registry from get_available_tools()

        Returns:
            Result text to send back to the model
        """
        if tool_id not in registry:
            return f"Error: Unknown MCP tool_id '{tool_id}'"

        entry = registry[tool_id]
        connection_id = str(entry.get("connection_id") or "")
        original_name = str(entry.get("tool_name") or "")
        input_schema = entry.get("input_schema")
        if isinstance(input_schema, dict):
            try:
                validate_json_schema(instance=arguments, schema=input_schema)
            except JsonSchemaValidationError as exc:
                return f"Error: Invalid MCP arguments for '{tool_id}': {exc.message}"

        # Load connection with secrets for tool execution
        from app.connectors.mcp.store import mcp_connection_service

        connection = mcp_connection_service.get_connection(
            connection_id=connection_id,
            include_secret=True,
            _server_internal=True,
        )
        if not connection:
            return f"Error: MCP connection not found for tool_id '{tool_id}'"

        logger.info(
            "Executing MCP tool: %s (original: %s, connection: %s)",
            tool_id, original_name, connection.get("name", connection_id),
        )

        try:
            from app.providers.mcp.client import call_tool

            result = call_tool(
                tool_name=original_name,
                arguments=arguments,
                server_url=connection.get("server_url") or "",
                auth_type=connection.get("auth_type", "none"),
                auth_config=connection.get("auth_config"),
                transport=connection.get("transport", "sse"),
                stdio_config=connection.get("stdio_config"),
            )

            return result

        except Exception as e:
            logger.error("MCP tool execution failed for %s: %s", tool_id, e)
            return f"Error executing MCP tool '{original_name}': {str(e)}"


def parse_mcp_arguments_json(arguments_json: str) -> tuple[Dict[str, Any], str | None]:
    """Parse the model-visible MCP arguments JSON string into an object."""
    try:
        parsed = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        return {}, f"Error: arguments_json must be valid JSON: {exc.msg}"
    if not isinstance(parsed, dict):
        return {}, "Error: arguments_json must decode to a JSON object"
    return parsed, None


# Singleton instance
mcp_tool_service = McpToolService()
