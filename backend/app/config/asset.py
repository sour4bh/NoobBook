"""
Asset registry for typed tool-spec search paths.

This module is the single source of truth for where domain-owned
``tools/specs.py`` modules live. Domain tickets register domain-owned
destinations here; loaders resolve tool specs through the registry only.

Tool contracts are registry-only after NBB-1104. Stable catalog keys map to
domain-owned spec modules here; checked-in JSON tool files are not a live
contract surface.
Built-in prompts are Python ``PromptSpec`` modules discovered by
``app.config.prompt`` and do not register through this asset loader.
"""
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# (category, tool_name) -> ordered list of directories to search for a single
# tool spec.
_tool_file_dirs: Dict[Tuple[str, str], List[Path]] = {}

# category -> ordered list of directories to search when a whole category has
# moved. `tool_loader.load_tool_specs_for_agent` consults these.
_tool_category_dirs: Dict[str, List[Path]] = {}


def register_tool_path(category: str, tool_name: str, directory: Path) -> None:
    """Register a domain-owned directory for a single tool spec.

    Per-file registrations win over per-category registrations. This lets a
    heterogeneous catalog family like `chat_tools/` span multiple domain
    owners without checked-in JSON tool files.
    """
    _tool_file_dirs.setdefault((category, tool_name), []).append(Path(directory))


def register_tool_category(category: str, directory: Path) -> None:
    """Register a domain-owned directory for an entire tool category.

    Used when a whole catalog family (e.g., `pdf_tools`) belongs to a single
    domain destination. `tool_loader.load_tool_specs_for_agent` consults this
    registration.
    """
    _tool_category_dirs.setdefault(category, []).append(Path(directory))


def iter_tool_category_dirs(category: str) -> List[Path]:
    """Return registered directories for a tool category in priority order."""
    dirs: List[Path] = list(_tool_category_dirs.get(category, []))
    return dirs


def registered_tool_categories() -> List[str]:
    """Return the tool categories that have any registered domain-owned dir."""
    categories: List[str] = []
    seen: set[str] = set()
    for category in _tool_category_dirs.keys():
        categories.append(category)
        seen.add(category)
    for category, _tool_name in _tool_file_dirs.keys():
        if category not in seen:
            categories.append(category)
            seen.add(category)
    return categories


def iter_tool_file_candidate_dirs(category: str) -> List[Tuple[str, Path]]:
    """Return exact per-file registration dirs for a category."""
    candidates: List[Tuple[str, Path]] = []
    for (registered_category, tool_name), dirs in _tool_file_dirs.items():
        if registered_category != category:
            continue
        candidates.extend((tool_name, directory) for directory in dirs)
    return candidates


def _reset_for_tests() -> None:
    """Clear every registration. Intended only for test fixtures."""
    _tool_file_dirs.clear()
    _tool_category_dirs.clear()


def _snapshot() -> Dict[str, Dict]:
    """Return a deep-ish snapshot of registry state for diagnostics/tests."""
    return {
        "tool_file_dirs": {k: list(v) for k, v in _tool_file_dirs.items()},
        "tool_category_dirs": {k: list(v) for k, v in _tool_category_dirs.items()},
    }


# Tool categories that have moved to domain-owned homes. The autouse reset
# fixture in `backend/tests/config/test_asset.py` replays these paths so tests
# can mutate the registry without leaking state.
#
# Key: category (the first argument to `tool_loader.load_tool_spec` /
# `load_tool_specs_for_agent`, and the `AGENT_NAME` value for agent services).
# Consumers keep using the same key; only the
# directory resolves to the new domain path.
# Value: directory path relative to `backend/app/`.
_PRODUCTION_TOOL_PATHS: Dict[str, str] = {
    "pdf_tools": "sources/pdf/tools",
    "pptx_tools": "sources/pptx/tools",
    "image_tools": "sources/image/tools",
    "web_agent": "sources/link/tools",
    "deep_research": "sources/analysis/research/tools",
    "analysis_agent": "sources/analysis/csv/raw_tools",
    "website_agent": "studio/design/website/tools",
    "component_agent": "studio/design/component/tools",
    "wireframe_agent": "studio/design/wireframe/tools",
    "blog_agent": "studio/documents/blog/tools",
    "business_report_agent": "studio/documents/business_report/tools",
    "prd_agent": "studio/documents/prd/tools",
    "presentation_agent": "studio/documents/presentation/tools",
    "email_agent": "studio/marketing/email/tools",
    "marketing_strategy_agent": "studio/marketing/strategy/tools",
}


# Single tool specs (not full categories) that have moved to domain-owned
# homes. Use per-tool entries when a directory contains specs owned by
# multiple loader categories, so category enumeration stays precise.
#
# Key: (category, tool_name) — the arguments to `tool_loader.load_tool_spec`.
# Value: directory path relative to `backend/app/` for the tool's `specs.py`.
_PRODUCTION_TOOL_FILE_PATHS: Dict[Tuple[str, str], str] = {
    ("chat_tools", "source_search_tool"): "chat/tools",
    ("chat_tools", "memory_tool"): "chat/memory/tools",
    ("chat_tools", "analyze_csv_agent_tool"): "sources/analysis/csv/tools",
    (
        "chat_tools",
        "analyze_database_agent_tool",
    ): "sources/analysis/database/tools",
    (
        "chat_tools",
        "analyze_freshdesk_agent_tool",
    ): "sources/analysis/freshdesk/tools",
    ("chat_tools", "studio_signal_tool"): "studio/signal/tools",
    ("chat_tools", "jira_get_issue"): "connectors/jira/tools",
    ("chat_tools", "jira_get_project"): "connectors/jira/tools",
    ("chat_tools", "jira_list_projects"): "connectors/jira/tools",
    ("chat_tools", "jira_search_issues"): "connectors/jira/tools",
    ("chat_tools", "notion_get_database_schema"): "connectors/notion/tools",
    ("chat_tools", "notion_query_database"): "connectors/notion/tools",
    ("chat_tools", "notion_read_page"): "connectors/notion/tools",
    ("chat_tools", "notion_search"): "connectors/notion/tools",
    ("chat_tools", "mixpanel_jql"): "connectors/mixpanel/tools",
    ("chat_tools", "mixpanel_list_events"): "connectors/mixpanel/tools",
    ("chat_tools", "mixpanel_list_funnels"): "connectors/mixpanel/tools",
    ("chat_tools", "mixpanel_query_events"): "connectors/mixpanel/tools",
    ("chat_tools", "mixpanel_query_funnel"): "connectors/mixpanel/tools",
    ("chat_tools", "mixpanel_retention"): "connectors/mixpanel/tools",
    ("chat_tools", "mixpanel_segmentation"): "connectors/mixpanel/tools",
    ("memory_tools", "manage_memory_tool"): "chat/memory/tools",
    ("csv_tool", "csv_analyser"): "sources/analysis/csv/tools",
    ("csv_tool", "return_csv_summary"): "sources/analysis/csv/tools",
    ("database_agent", "query_runner"): "sources/analysis/database/tools",
    (
        "database_agent",
        "return_database_result",
    ): "sources/analysis/database/tools",
    ("database_agent", "schema_fetcher"): "sources/analysis/database/tools",
    ("freshdesk_agent", "query_runner"): "sources/analysis/freshdesk/tools",
    (
        "freshdesk_agent",
        "return_ticket_analysis",
    ): "sources/analysis/freshdesk/tools",
    ("freshdesk_agent", "schema_info"): "sources/analysis/freshdesk/tools",
    ("studio_tools", "flow_diagram_tool"): "studio/design/flow_diagram/tools",
    ("studio_tools", "wireframe_tool"): "studio/design/wireframe/tools",
    ("studio_tools", "flash_cards_tool"): "studio/learning/flash_card/tools",
    ("studio_tools", "mind_map_tool"): "studio/learning/mind_map/tools",
    ("studio_tools", "quiz_tool"): "studio/learning/quiz/tools",
    ("studio_tools", "read_source_content"): "studio/media/audio/tools",
    ("studio_tools", "write_script_section"): "studio/media/audio/tools",
}


def register_production_asset_paths() -> None:
    """Register every domain-owned tool-spec path.

    Called from `app.config` package init so `tool_loader` singletons see the
    registered paths before any consumer imports them.
    Idempotent: calling twice appends the same dirs twice, so callers must
    reset the registry (tests) or rely on the single package-init call
    (production).
    """
    app_dir = Path(__file__).resolve().parents[1]
    for category, relative in _PRODUCTION_TOOL_PATHS.items():
        register_tool_category(category, app_dir / relative)
    for (category, tool_name), relative in _PRODUCTION_TOOL_FILE_PATHS.items():
        register_tool_path(category, tool_name, app_dir / relative)
