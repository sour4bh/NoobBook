"""
Chat-owned tool registry surface.

This is the public entry point that route- and domain-layer code uses to
discover the tool JSON schemas chat exposes to Claude. It names the stable
chat tool file keys and delegates loading to the asset registry.

Trace: NBB-207C tool-schema ownership inventory + the tool-schema JSON
contract in `docs/contracts/README.md` (NBB-205 Contract 11).
"""
from typing import Any, Dict, Tuple

from app.config.tool import tool_loader


# Static names of every chat-owned tool JSON loaded through the `chat_tools`
# compatibility key. Order is informational, not contractual.
CHAT_TOOL_NAMES: Tuple[str, ...] = (
    "source_search_tool",
    "memory_tool",
    "studio_signal_tool",
    "analyze_csv_agent_tool",
    "analyze_database_agent_tool",
    "analyze_freshdesk_agent_tool",
)


def get_tool(name: str) -> Dict[str, Any]:
    """Load a chat-owned tool JSON by name through the asset registry.

    `tool_loader.load_tool` honors the registry mappings, so the legacy
    category key remains stable while files live under domain-owned paths.
    """
    return tool_loader.load_tool("chat_tools", name)
