"""
Asset registry for prompt JSON and tool JSON search paths.

This module is the single source of truth for where prompt and tool JSON files
live. Domain tickets register domain-owned destinations here; loaders resolve
assets through the registry only.

Tool schemas are registry-only after NBB-810. Category API compatibility is
preserved by mapping legacy category/name keys to domain-owned files here, not
by keeping a fallback directory alive.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# prompt_name -> ordered list of directories to search.
# `prompt_name` matches the argument to `prompt_loader.get_prompt_config`
# (e.g., "memory" for `memory_prompt.json`) and the file stem used by
# `get_agent_prompt`.
_prompt_dirs: Dict[str, List[Path]] = {}

# (category, tool_name) -> ordered list of directories to search for a single
# tool JSON.
_tool_file_dirs: Dict[Tuple[str, str], List[Path]] = {}

# category -> ordered list of directories to search when a whole category has
# moved. `load_tools_from_category` and `load_tools_for_agent` consult these.
_tool_category_dirs: Dict[str, List[Path]] = {}


class AssetNotFoundError(FileNotFoundError):
    """Raised when an asset key resolves to no existing file.

    Subclasses `FileNotFoundError` so existing callers that already catch
    `FileNotFoundError` (e.g., `tool_loader.load_tool`) keep working.
    """


def register_prompt_path(prompt_name: str, directory: Path) -> None:
    """Register a domain-owned directory for a single prompt.

    Registered paths are searched in registration order. A registered
    directory that does not contain the expected file falls through to the next
    candidate.
    """
    _prompt_dirs.setdefault(prompt_name, []).append(Path(directory))


def register_tool_path(category: str, tool_name: str, directory: Path) -> None:
    """Register a domain-owned directory for a single tool JSON file.

    Per-file registrations win over per-category registrations. This lets a
    heterogeneous legacy category like `chat_tools/` be split across multiple
    new owners one file at a time.
    """
    _tool_file_dirs.setdefault((category, tool_name), []).append(Path(directory))


def register_tool_category(category: str, directory: Path) -> None:
    """Register a domain-owned directory for an entire tool category.

    Used when a whole legacy family (e.g., `pdf_tools/`) moves to a single
    domain destination. `load_tools_from_category` / `load_tools_for_agent`
    consult this registration.
    """
    _tool_category_dirs.setdefault(category, []).append(Path(directory))


def iter_prompt_candidate_paths(prompt_name: str, filename: str) -> List[Path]:
    """Return candidate prompt file paths in priority order.

    Prompts are registry-only after NBB-812.
    """
    return [
        directory / filename for directory in _prompt_dirs.get(prompt_name, [])
    ]


def iter_tool_candidate_paths(
    category: str, tool_name: str, _registry_root: Path
) -> List[Path]:
    """Return candidate tool JSON file paths in priority order.

    Per-tool registrations win over per-category registrations. Tools do not
    fall back to the legacy tool directory; every live tool path must be
    registered.
    """
    filename = f"{tool_name}.json"
    candidates: List[Path] = [
        directory / filename
        for directory in _tool_file_dirs.get((category, tool_name), [])
    ]
    candidates.extend(
        directory / filename for directory in _tool_category_dirs.get(category, [])
    )
    return candidates


def iter_tool_category_dirs(category: str, _registry_root: Path) -> List[Path]:
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


def iter_tool_file_candidate_paths(category: str) -> List[Path]:
    """Return exact per-file registrations for a category in priority order."""
    candidates: List[Path] = []
    for (registered_category, tool_name), dirs in _tool_file_dirs.items():
        if registered_category != category:
            continue
        filename = f"{tool_name}.json"
        candidates.extend(directory / filename for directory in dirs)
    return candidates


def resolve_prompt_path(prompt_name: str, filename: str) -> Path:
    """Return the first existing candidate prompt file, or raise.

    Internal resolver used by loaders that want an explicit miss signal. Public
    loader methods may still convert the raise into their existing contract
    (e.g., `get_prompt_config` returning `None`).
    """
    for candidate in iter_prompt_candidate_paths(prompt_name, filename):
        if candidate.exists():
            return candidate
    raise AssetNotFoundError(
        f"Prompt asset not found: name={prompt_name!r}, filename={filename!r}. "
        f"Searched registered directories for {prompt_name!r}. Prompts are "
        f"registry-only after NBB-812."
    )


def resolve_tool_path(category: str, tool_name: str, legacy_dir: Path) -> Path:
    """Return the first existing candidate tool file, or raise.

    Internal resolver used by loaders that want an explicit miss signal.
    """
    for candidate in iter_tool_candidate_paths(category, tool_name, legacy_dir):
        if candidate.exists():
            return candidate
    raise AssetNotFoundError(
        f"Tool asset not found: category={category!r}, tool={tool_name!r}. "
        f"Searched registered per-file and per-category paths. Tools are "
        f"registry-only after NBB-810."
    )


def iter_registered_prompt_dirs() -> List[Tuple[str, Path]]:
    """Return every (prompt_name, directory) pair currently registered.

    Used by `list_all_prompts` to enumerate domain-owned prompt files without
    re-discovering the directories elsewhere.
    """
    pairs: List[Tuple[str, Path]] = []
    for prompt_name, dirs in _prompt_dirs.items():
        for directory in dirs:
            pairs.append((prompt_name, directory))
    return pairs


def _reset_for_tests() -> None:
    """Clear every registration. Intended only for test fixtures."""
    _prompt_dirs.clear()
    _tool_file_dirs.clear()
    _tool_category_dirs.clear()


def _snapshot() -> Dict[str, Dict]:
    """Return a deep-ish snapshot of registry state for diagnostics/tests."""
    return {
        "prompt_dirs": {k: list(v) for k, v in _prompt_dirs.items()},
        "tool_file_dirs": {k: list(v) for k, v in _tool_file_dirs.items()},
        "tool_category_dirs": {k: list(v) for k, v in _tool_category_dirs.items()},
    }


# Prompts that have moved to domain-owned homes. The map lives here
# so it can be replayed after `_reset_for_tests()` during tests that need the
# production configuration restored.
#
# Key: prompt_name (the argument passed to `prompt_loader.get_prompt_config`).
# Value: directory path relative to `backend/app/`.
_PRODUCTION_PROMPT_PATHS: Dict[str, str] = {
    "default": "chat/prompts",
    "chat_naming": "chat/prompts",
    "memory": "chat/memory/prompts",
    "summary": "sources/prompts",
    "csv_analyzer_agent": "sources/analysis/csv/prompts",
    "csv_processor": "sources/analysis/csv/prompts",
    "database_analyzer_agent": "sources/analysis/database/prompts",
    "freshdesk_analyzer_agent": "sources/analysis/freshdesk/prompts",
    "pdf_extraction": "sources/pdf/prompts",
    "pptx_extraction": "sources/pptx/prompts",
    "image_extraction": "sources/image/prompts",
    "web_agent": "sources/link/prompts",
    "deep_research_agent": "sources/analysis/research/prompts",
    "website_agent": "studio/design/website/prompts",
    "component_agent": "studio/design/component/prompts",
    "flow_diagram": "studio/design/flow_diagram/prompts",
    "wireframe": "studio/design/wireframe/prompts",
    "wireframe_agent": "studio/design/wireframe/prompts",
    "blog_agent": "studio/documents/blog/prompts",
    "business_report_agent": "studio/documents/business_report/prompts",
    "prd_agent": "studio/documents/prd/prompts",
    "presentation_agent": "studio/documents/presentation/prompts",
    "ad_creative": "studio/marketing/ad/prompts",
    "email_agent": "studio/marketing/email/prompts",
    "infographic": "studio/marketing/infographic/prompts",
    "marketing_strategy_agent": "studio/marketing/strategy/prompts",
    "social_posts": "studio/marketing/social_post/prompts",
    "flash_cards": "studio/learning/flash_card/prompts",
    "mind_map": "studio/learning/mind_map/prompts",
    "quiz": "studio/learning/quiz/prompts",
    "audio_script": "studio/media/audio/prompts",
    "video": "studio/media/video/prompts",
}


# Tool categories that have moved to domain-owned homes (NBB-207C). Paired
# with `_PRODUCTION_PROMPT_PATHS` so both asset types replay through one
# function; the autouse reset fixture in
# `backend/tests/config/test_asset.py` has a single replay hook.
#
# Key: category (the first argument to `tool_loader.load_tool` /
# `load_tools_from_category` / `load_tools_for_agent`, and the `AGENT_NAME`
# value for agent services). Consumers keep using the same key; only the
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


# Single tool JSON files (not full categories) that have moved to domain-owned
# homes. Use per-file entries when a directory contains schemas owned by
# multiple loader categories, so category enumeration stays precise.
#
# Key: (category, tool_name) — the arguments to `tool_loader.load_tool`.
# Value: directory path relative to `backend/app/` for the tool's JSON file.
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
    """Register every domain-owned prompt/tool JSON path.

    Called from `app.config` package init so `prompt_loader`/`tool_loader`
    singletons see the registered paths before any consumer imports them.
    Idempotent: calling twice appends the same dirs twice, so callers must
    reset the registry (tests) or rely on the single package-init call
    (production).
    """
    app_dir = Path(__file__).resolve().parents[1]
    for prompt_name, relative in _PRODUCTION_PROMPT_PATHS.items():
        register_prompt_path(prompt_name, app_dir / relative)
    for category, relative in _PRODUCTION_TOOL_PATHS.items():
        register_tool_category(category, app_dir / relative)
    for (category, tool_name), relative in _PRODUCTION_TOOL_FILE_PATHS.items():
        register_tool_path(category, tool_name, app_dir / relative)
