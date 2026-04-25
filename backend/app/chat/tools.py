"""
Chat-owned tool registry surface.

This is the public entry point that route- and domain-layer code uses to
discover the tool JSON schemas chat exposes to Claude. It is intentionally
thin in NBB-301 — capability-aware exposure (filtered by the source set,
user permissions, and the `ToolCapabilityPolicy` from NBB-202B) lands in
NBB-303. Until then this module names the chat-owned tool JSON files and
delegates loading to the asset registry from NBB-207A / NBB-207C.

Trace: NBB-207C tool-schema ownership inventory + the tool-schema JSON
contract in `docs/contracts/README.md` (NBB-205 Contract 11).
"""
from typing import Any, Dict, Tuple

from app.config.tool_loader import tool_loader


# Static names of every chat-owned tool JSON in the `chat_tools` category
# (see NBB-207C). Order is informational, not contractual: capability
# filtering and ordering policy are NBB-303's job.
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

    `tool_loader.load_tool` honors the registry shims from NBB-207A, so this
    keeps working when prompt/tool JSON ownership moves under NBB-207C.
    """
    return tool_loader.load_tool("chat_tools", name)
