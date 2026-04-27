"""
Chat tool availability and capability-aware exposure.

Owns the lazy tool-definition cache and the per-turn `select_tools` call
that gates every Claude-visible tool through `ToolCapabilityPolicy`
(NBB-202B). Memory and studio_signal are always candidates; search is
gated by non-CSV active sources; analyzer tools by their respective
source kinds; Jira/Mixpanel by project-scoped sources; KB tools by
configuration; MCP tools by per-user connections.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.auth.tool_capabilities import mcp_capability_for
from app.auth.tool_policy import tool_capability_policy
from app.config.tool import tool_loader
from app.connectors.knowledge import knowledge_base_service
from app.connectors.mcp.tools import mcp_tool_service


logger = logging.getLogger(__name__)


class ChatToolPolicy:
    """Cache tool JSON definitions and assemble the per-turn tools list.

    Every tool exposure goes through `ToolCapabilityPolicy.is_exposable_for`
    (NBB-202B AC#2): missing `user_id` fails closed, and any tool without a
    capability entry is refused. MCP tool names are dynamic, so synthesized
    capability entries are registered before the exposure check runs.
    """

    def __init__(self) -> None:
        self._search_tool: Optional[Dict[str, Any]] = None
        self._memory_tool: Optional[Dict[str, Any]] = None
        self._csv_analyzer_tool: Optional[Dict[str, Any]] = None
        self._database_analyzer_tool: Optional[Dict[str, Any]] = None
        self._freshdesk_analyzer_tool: Optional[Dict[str, Any]] = None
        self._studio_signal_tool: Optional[Dict[str, Any]] = None

    def _get_search_tool(self) -> Dict[str, Any]:
        if self._search_tool is None:
            self._search_tool = tool_loader.load_tool("chat_tools", "source_search_tool")
        return self._search_tool

    def _get_memory_tool(self) -> Dict[str, Any]:
        if self._memory_tool is None:
            self._memory_tool = tool_loader.load_tool("chat_tools", "memory_tool")
        return self._memory_tool

    def _get_csv_analyzer_tool(self) -> Dict[str, Any]:
        if self._csv_analyzer_tool is None:
            self._csv_analyzer_tool = tool_loader.load_tool("chat_tools", "analyze_csv_agent_tool")
        return self._csv_analyzer_tool

    def _get_database_analyzer_tool(self) -> Dict[str, Any]:
        if self._database_analyzer_tool is None:
            self._database_analyzer_tool = tool_loader.load_tool(
                "chat_tools", "analyze_database_agent_tool"
            )
        return self._database_analyzer_tool

    def _get_freshdesk_analyzer_tool(self) -> Dict[str, Any]:
        if self._freshdesk_analyzer_tool is None:
            self._freshdesk_analyzer_tool = tool_loader.load_tool(
                "chat_tools", "analyze_freshdesk_agent_tool"
            )
        return self._freshdesk_analyzer_tool

    def _get_studio_signal_tool(self) -> Dict[str, Any]:
        if self._studio_signal_tool is None:
            self._studio_signal_tool = tool_loader.load_tool("chat_tools", "studio_signal_tool")
        return self._studio_signal_tool

    def select_tools(
        self,
        *,
        has_active_sources: bool,
        has_csv_sources: bool = False,
        has_database_sources: bool = False,
        has_freshdesk_sources: bool = False,
        has_jira_sources: bool = False,
        has_mixpanel_sources: bool = False,
        user_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict]:
        """Return (tools_list, mcp_registry) for one Claude API call."""
        # Capability-aware tool selection. Every Claude-visible tool
        # is gated by ``ToolCapabilityPolicy.is_exposable_for``, which
        # both enforces NBB-202A fail-closed semantics for missing
        # ``user_id`` and refuses to expose any tool without a
        # capability entry. The previous ``not user_id or ...``
        # short-circuits silently allowed unknown identities; routing
        # the decision through the policy closes that gap and means
        # NBB-202B's AC#2 is enforced at this single call site.
        tool_capability_policy.ensure_capabilities_loaded()

        def _exposable(tool_name: str) -> bool:
            return tool_capability_policy.is_exposable_for(user_id, tool_name)

        tools: List[Dict[str, Any]] = []

        if _exposable("store_memory"):
            tools.append(self._get_memory_tool())

        if _exposable("studio_signal"):
            tools.append(self._get_studio_signal_tool())

        if has_active_sources and _exposable("search_sources"):
            tools.append(self._get_search_tool())

        if has_csv_sources and _exposable("analyze_csv_agent"):
            tools.append(self._get_csv_analyzer_tool())

        if has_database_sources and _exposable("analyze_database_agent"):
            tools.append(self._get_database_analyzer_tool())

        if has_freshdesk_sources and _exposable("analyze_freshdesk_agent"):
            tools.append(self._get_freshdesk_analyzer_tool())

        # Add Jira tools only when the project has a .jira source (project-scoped).
        # Each tool is filtered through the policy individually so a stale
        # KnowledgeBaseService cache cannot expose a tool the policy denies.
        if has_jira_sources:
            for jira_tool in knowledge_base_service.get_jira_tools():
                if _exposable(jira_tool["name"]):
                    tools.append(jira_tool)

        # Add Mixpanel tools only when the project has a .mixpanel source (project-scoped)
        if has_mixpanel_sources:
            for mp_tool in knowledge_base_service.get_mixpanel_tools():
                if _exposable(mp_tool["name"]):
                    tools.append(mp_tool)

        # Non-Jira knowledge base tools (Notion, GitHub, etc.) — always global
        for kb_tool in knowledge_base_service.get_available_tools():
            if _exposable(kb_tool["name"]):
                tools.append(kb_tool)

        # Add MCP tools if user has tool-enabled connections. Per-server
        # tool names are dynamic; register a synthesized capability
        # entry for each one before checking exposure so the policy
        # decision still runs through ``is_exposable_for``.
        mcp_registry: Dict = {}
        if user_id:
            try:
                mcp_tools, mcp_registry = mcp_tool_service.get_available_tools(user_id=user_id)
                exposed_mcp_tools = []
                for mcp_tool in mcp_tools:
                    name = mcp_tool["name"]
                    if not tool_capability_policy.has(name):
                        tool_capability_policy.register(mcp_capability_for(name))
                    if _exposable(name):
                        exposed_mcp_tools.append(mcp_tool)
                if exposed_mcp_tools:
                    tools.extend(exposed_mcp_tools)
                    logger.info(
                        "Added %d MCP tools for user %s",
                        len(exposed_mcp_tools),
                        user_id,
                    )
            except Exception as e:
                logger.error("Failed to load MCP tools for user %s: %s", user_id, e)

        return tools, mcp_registry


chat_tool_policy = ChatToolPolicy()
