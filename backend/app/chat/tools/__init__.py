"""
Chat-owned tool registry surface.

This is the public entry point that route- and domain-layer code uses to
discover the typed tool contracts chat exposes to model providers. It names
the stable chat tool keys and delegates loading to the asset registry.

Trace: NBB-207C tool-schema ownership inventory, NBB-810 services-tool drain,
and NBB-1104 typed ToolSpec conversion.
"""
from typing import Tuple

from app.config.tool import tool_loader


# Static names of every chat-owned ToolSpec loaded through the `chat_tools`
# catalog key. Order is informational, not contractual.
CHAT_TOOL_NAMES: Tuple[str, ...] = (
    "source_search_tool",
    "memory_tool",
    "studio_signal_tool",
    "analyze_csv_agent_tool",
    "analyze_database_agent_tool",
    "analyze_freshdesk_agent_tool",
)


def get_tool(name: str):
    """Load a chat-owned tool spec by name through the asset registry.

    Provider adapters compile the spec into concrete provider schemas at the
    runtime boundary.
    """
    return tool_loader.load_tool_spec("chat_tools", name)
