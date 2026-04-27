"""
Tests for NBB-207C tool-schema ownership and tool-loader compatibility.

These assert that registered domain-owned tool paths resolve end-to-end and
both `load_tool` and `load_tools_for_agent` see the registered paths via the
production singleton. Tool schemas are registry-only after NBB-810.

The sibling `test_asset.py` autouse fixture resets the registry
before and after each test; these tests explicitly re-invoke
`register_production_asset_paths()` after reset so they see the state a
running backend sees at startup. This mirrors the pattern established by
`test_prompt_loader_registry.py` for NBB-207B.
"""
from typing import List, Tuple

import pytest

import app.config.asset as asset
from app.config.tool import ToolLoader, tool_loader


# Tool families moved to domain-owned homes in NBB-207C. Each entry carries the
# loader category key (unchanged; consumers keep passing it), the expected
# relative destination dir, the client-tool stems (loadable via
# `load_tool`), and the full tool-stem list (what
# `load_tools_from_category` returns, including server tools that carry no
# `input_schema` and therefore cannot be loaded via the validating
# `load_tool`).
MOVED_TOOL_FAMILIES: List[Tuple[str, str, List[str], List[str]]] = [
    (
        "chat_tools",
        "mixed domain-owned paths",
        [
            "source_search_tool",
            "memory_tool",
            "studio_signal_tool",
            "analyze_csv_agent_tool",
            "analyze_database_agent_tool",
            "analyze_freshdesk_agent_tool",
            "jira_get_issue",
            "jira_get_project",
            "jira_list_projects",
            "jira_search_issues",
            "notion_get_database_schema",
            "notion_query_database",
            "notion_read_page",
            "notion_search",
            "mixpanel_jql",
            "mixpanel_list_events",
            "mixpanel_list_funnels",
            "mixpanel_query_events",
            "mixpanel_query_funnel",
            "mixpanel_retention",
            "mixpanel_segmentation",
        ],
        [
            "source_search_tool",
            "memory_tool",
            "studio_signal_tool",
            "analyze_csv_agent_tool",
            "analyze_database_agent_tool",
            "analyze_freshdesk_agent_tool",
            "jira_get_issue",
            "jira_get_project",
            "jira_list_projects",
            "jira_search_issues",
            "notion_get_database_schema",
            "notion_query_database",
            "notion_read_page",
            "notion_search",
            "mixpanel_jql",
            "mixpanel_list_events",
            "mixpanel_list_funnels",
            "mixpanel_query_events",
            "mixpanel_query_funnel",
            "mixpanel_retention",
            "mixpanel_segmentation",
        ],
    ),
    ("pdf_tools", "sources/pdf/tools", ["pdf_extraction"], ["pdf_extraction"]),
    (
        "pptx_tools",
        "sources/pptx/tools",
        ["pptx_extraction"],
        ["pptx_extraction"],
    ),
    (
        "image_tools",
        "sources/image/tools",
        ["image_extraction"],
        ["image_extraction"],
    ),
    (
        "web_agent",
        "sources/link/tools",
        ["return_search_result", "tavily_search"],
        ["return_search_result", "tavily_search", "web_search"],
    ),
    (
        "deep_research",
        "sources/analysis/research/tools",
        ["tavily_search_advance", "write_research_to_file"],
        ["tavily_search_advance", "web_search", "write_research_to_file"],
    ),
    # NBB-403/NBB-907: csv/database/freshdesk analysis JSONs land under
    # sources/analysis/<feature>/tools. analysis_agent (declarative CSV
    # operation tools) and csv_tool (summary tools) keep distinct directories
    # because each has its own loader category and tool-name set.
    (
        "analysis_agent",
        "sources/analysis/csv/raw_tools",
        ["return_analysis", "run_analysis"],
        ["return_analysis", "run_analysis"],
    ),
    ("csv_tool", "sources/analysis/csv/tools", ["csv_analyser", "return_csv_summary"], ["csv_analyser", "return_csv_summary"]),
    (
        "database_agent",
        "sources/analysis/database/tools",
        ["query_runner", "return_database_result", "schema_fetcher"],
        ["query_runner", "return_database_result", "schema_fetcher"],
    ),
    (
        "freshdesk_agent",
        "sources/analysis/freshdesk/tools",
        ["query_runner", "return_ticket_analysis", "schema_info"],
        ["query_runner", "return_ticket_analysis", "schema_info"],
    ),
    (
        "memory_tools",
        "chat/memory/tools",
        ["manage_memory_tool"],
        ["manage_memory_tool"],
    ),
]


@pytest.fixture(autouse=True)
def _restore_production_registry():
    """Replay production registrations after the sibling reset fixture runs.

    The autouse fixture in `test_asset.py` calls
    `_reset_for_tests()` between every test in this directory. Production
    registration happens exactly once at `app.config` import, so once the
    reset fires the real paths are gone for the rest of the session. Replay
    them here to restore the state under test.
    """
    asset._reset_for_tests()
    asset.register_production_asset_paths()
    yield
    asset._reset_for_tests()


def _fresh_loader() -> ToolLoader:
    """Build a fresh ToolLoader with production registry paths."""
    return ToolLoader()


@pytest.mark.parametrize(
    "category,relative_dir,client_stems,all_stems",
    MOVED_TOOL_FAMILIES,
    ids=[category for category, _, _, _ in MOVED_TOOL_FAMILIES],
)
def test_moved_tool_family_resolves_from_registered_domain_path(
    category: str,
    relative_dir: str,
    client_stems: List[str],
    all_stems: List[str],
) -> None:
    """Each NBB-207C move must resolve via the registered domain dir.

    Failure here means the tool JSON moved but the registry pointer did
    not, or vice versa — either way, production `load_tool` would raise
    `FileNotFoundError` on a category that used to work.

    Only client tools are loaded via `load_tool`: server tools (e.g.
    `web_search`) carry only `type`/`name`/`max_uses` and fail the
    `load_tool` validator, which is why agents use `load_tools_for_agent`
    for those.
    """
    loader = _fresh_loader()

    for tool_stem in client_stems:
        tool = loader.load_tool(category, tool_stem)
        assert "name" in tool, (
            f"registered tool {category}/{tool_stem} did not load"
        )

    # Confirm no same-named legacy category directory is being used.
    legacy_category_dir = loader.tools_dir / category
    if legacy_category_dir.exists():
        remaining = list(legacy_category_dir.glob("*.json"))
        assert remaining == [], (
            f"legacy dir {legacy_category_dir} should be drained, found {remaining}"
        )


@pytest.mark.parametrize(
    "category,relative_dir,client_stems,all_stems",
    MOVED_TOOL_FAMILIES,
    ids=[category for category, _, _, _ in MOVED_TOOL_FAMILIES],
)
def test_moved_tool_family_enumerates_every_tool(
    category: str,
    relative_dir: str,
    client_stems: List[str],
    all_stems: List[str],
) -> None:
    """`load_tools_for_agent` must see every tool in the new dir.

    Agents like `web_agent_service` enumerate the whole category. If the
    registered dir loses a file we would silently drop a tool from the
    agentic loop. `load_tools_for_agent` is the right entry point because
    it handles server tools (no `input_schema`) and client tools together;
    `load_tools_from_category` calls the same validator that `load_tool`
    calls and therefore rejects server-tool JSON by shape.
    """
    loader = _fresh_loader()

    bundle = loader.load_tools_for_agent(category)
    loaded_names = {t["name"] for t in bundle["all_tools"]}

    # `all_stems` is every file in the moved directory. Server tools appear
    # under `server_tools`, client tools under `client_tools`; `all_tools`
    # unions both, and the unique tool-name count should match the number
    # of moved files.
    assert len(bundle["all_tools"]) == len(all_stems), (
        f"{category}: expected {len(all_stems)} tools "
        f"({all_stems}), got {len(bundle['all_tools'])} ({loaded_names})"
    )


def test_chat_tools_category_excludes_deleted_compact_tool() -> None:
    """The dormant compact tool was deleted instead of exposed."""
    loader = _fresh_loader()

    tools = loader.load_tools_from_category("chat_tools")
    names = {tool["name"] for tool in tools}

    assert "compact" not in names


def test_singleton_sees_registered_tool_paths() -> None:
    """The `tool_loader` singleton must see production registrations.

    Services cache `tool_loader.load_tool(...)` results at first use; this
    covers the path real runtime callers take, not a freshly built loader.
    """
    tool = tool_loader.load_tool("pdf_tools", "pdf_extraction")
    assert "name" in tool


def test_web_agent_load_tools_for_agent_returns_expected_split() -> None:
    """`load_tools_for_agent('web_agent')` must split server/client tools.

    `web_agent_service.py` depends on server tools (`web_search`) being
    separated from client tools (`tavily_search`, `return_search_result`).
    The registered path change must preserve that split.
    """
    bundle = tool_loader.load_tools_for_agent("web_agent")

    server_names = {t["name"] for t in bundle["server_tools"]}
    client_names = {t["name"] for t in bundle["client_tools"]}

    assert "web_search" in server_names
    assert {"tavily_search", "return_search_result"}.issubset(client_names)


def test_deep_research_load_tools_for_agent_returns_expected_split() -> None:
    """`load_tools_for_agent('deep_research')` must split server/client tools."""
    bundle = tool_loader.load_tools_for_agent("deep_research")

    server_names = {t["name"] for t in bundle["server_tools"]}
    client_names = {t["name"] for t in bundle["client_tools"]}

    assert "web_search" in server_names
    assert {"tavily_search_advance", "write_research_to_file"}.issubset(client_names)
