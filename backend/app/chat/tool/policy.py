"""
Chat tool availability and capability-aware exposure.

Owns the lazy ToolSpec cache and the per-turn `select_tools` call
that gates every model-visible tool through `ToolCapabilityPolicy`
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
from app.connectors.mcp.tools import MCP_PROXY_TOOL_NAME, mcp_tool_service


logger = logging.getLogger(__name__)


def _ensure_chat_capabilities_loaded() -> None:
    """Load capability entries needed by chat-exposed tools."""
    tool_capability_policy.ensure_capabilities_loaded()
    # Analysis tools are source-owned. Chat imports their registrations because
    # chat is the surface that can expose analyzer tools to the model; auth stays
    # a domain-independent policy primitive.
    import app.sources.analysis.tool_capabilities  # noqa: F401


def _load_tool(category: str, name: str) -> Any:
    return tool_loader.load_tool_spec(category, name)


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or "")
    return str(getattr(tool, "name", ""))


class ChatToolPolicy:
    """Cache compiled tool schemas and assemble the per-turn tools list.

    Every tool exposure goes through `ToolCapabilityPolicy.is_exposable_for`
    (NBB-202B AC#2): missing `user_id` fails closed, and any tool without a
    capability entry is refused. MCP tool names are dynamic, so synthesized
    capability entries are registered before the exposure check runs.
    """

    def __init__(self) -> None:
        self._search_tool: Optional[Any] = None
        self._memory_tool: Optional[Any] = None
        self._csv_analyzer_tool: Optional[Any] = None
        self._database_analyzer_tool: Optional[Any] = None
        self._freshdesk_analyzer_tool: Optional[Any] = None
        self._studio_signal_tool: Optional[Any] = None

    def _get_search_tool(self) -> Any:
        if self._search_tool is None:
            self._search_tool = _load_tool("chat_tools", "source_search_tool")
        return self._search_tool

    def _get_memory_tool(self) -> Any:
        if self._memory_tool is None:
            self._memory_tool = _load_tool("chat_tools", "memory_tool")
        return self._memory_tool

    def _get_csv_analyzer_tool(self) -> Any:
        if self._csv_analyzer_tool is None:
            self._csv_analyzer_tool = _load_tool("chat_tools", "analyze_csv_agent_tool")
        return self._csv_analyzer_tool

    def _get_database_analyzer_tool(self) -> Any:
        if self._database_analyzer_tool is None:
            self._database_analyzer_tool = _load_tool(
                "chat_tools", "analyze_database_agent_tool"
            )
        return self._database_analyzer_tool

    def _get_freshdesk_analyzer_tool(self) -> Any:
        if self._freshdesk_analyzer_tool is None:
            self._freshdesk_analyzer_tool = _load_tool(
                "chat_tools", "analyze_freshdesk_agent_tool"
            )
        return self._freshdesk_analyzer_tool

    def _get_studio_signal_tool(self) -> Any:
        if self._studio_signal_tool is None:
            self._studio_signal_tool = _load_tool("chat_tools", "studio_signal_tool")
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
        project_id: Optional[str] = None,
    ) -> Tuple[List[Any], Dict]:
        """Return (tools_list, mcp_registry) for one model call."""
        # Capability-aware tool selection. Every model-visible tool
        # is gated by ``ToolCapabilityPolicy.is_exposable_for``, which
        # both enforces NBB-202A fail-closed semantics for missing
        # ``user_id`` and refuses to expose any tool without a
        # capability entry. The previous ``not user_id or ...``
        # short-circuits silently allowed unknown identities; routing
        # the decision through the policy closes that gap and means
        # NBB-202B's AC#2 is enforced at this single call site.
        _ensure_chat_capabilities_loaded()

        def _exposable(tool_name: str) -> bool:
            return tool_capability_policy.is_exposable_for(user_id, tool_name)

        tools: List[Any] = []

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
            for jira_tool in knowledge_base_service.get_jira_tools(project_id=project_id):
                if _exposable(_tool_name(jira_tool)):
                    tools.append(jira_tool)

        # Add Mixpanel tools only when the project has a .mixpanel source (project-scoped)
        if has_mixpanel_sources:
            for mp_tool in knowledge_base_service.get_mixpanel_tools(project_id=project_id):
                if _exposable(_tool_name(mp_tool)):
                    tools.append(mp_tool)

        # Non-Jira knowledge base tools (Notion, GitHub, etc.) resolve through
        # the same project/workspace secret surface as project-scoped tools.
        for kb_tool in knowledge_base_service.get_available_tools(project_id=project_id):
            if _exposable(_tool_name(kb_tool)):
                tools.append(kb_tool)

        # Add the app-owned MCP proxy if the user has tool-enabled
        # connections. The individual MCP tool ids stay in the per-turn
        # registry/context; providers see one stable Pydantic proxy tool.
        mcp_registry: Dict = {}
        if user_id:
            try:
                mcp_tools, mcp_registry = mcp_tool_service.get_available_tools(user_id=user_id)
                proxy_tools = [
                    tool
                    for tool in mcp_tools
                    if _tool_name(tool) == MCP_PROXY_TOOL_NAME
                ]
                if proxy_tools and not tool_capability_policy.has(MCP_PROXY_TOOL_NAME):
                    tool_capability_policy.register(mcp_capability_for(MCP_PROXY_TOOL_NAME))
                if proxy_tools and _exposable(MCP_PROXY_TOOL_NAME):
                    tools.append(proxy_tools[0])
                    logger.info(
                        "Added MCP proxy for %d tools for user %s",
                        len(mcp_registry),
                        user_id,
                    )
            except Exception as e:
                logger.error("Failed to load MCP tools for user %s: %s", user_id, e)

        return tools, mcp_registry


chat_tool_policy = ChatToolPolicy()
