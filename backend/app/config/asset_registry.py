"""
Asset registry for prompt JSON and tool JSON search paths.

This module is the single source of truth for where prompt and tool JSON files
live during the structure migration. Domain tickets (NBB-207B for prompts,
NBB-207C for tool schemas) register domain-owned destinations here; the
loaders (`prompt_loader`, `tool_loader`) consult the registry first, then fall
back to the current legacy locations:

    - prompts: `backend/data/prompts/<name>_prompt.json`
    - tools:   `backend/app/services/tools/<category>/<tool>.json`

The registry does not move JSON assets itself. It only teaches the loaders
that a registered location should be tried before the legacy location for a
specific prompt name, tool (category, name) pair, or tool category.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# prompt_name -> ordered list of directories to search before the legacy path.
# `prompt_name` matches the argument to `prompt_loader.get_prompt_config`
# (e.g., "memory" for `memory_prompt.json`) and the file stem used by
# `get_agent_prompt`.
_prompt_dirs: Dict[str, List[Path]] = {}

# (category, tool_name) -> ordered list of directories to search before the
# legacy path for a single tool JSON.
_tool_file_dirs: Dict[Tuple[str, str], List[Path]] = {}

# category -> ordered list of directories to search before the legacy path
# when a whole category has moved. `load_tools_from_category` and
# `load_tools_for_agent` consult these.
_tool_category_dirs: Dict[str, List[Path]] = {}


class AssetNotFoundError(FileNotFoundError):
    """Raised when an asset key resolves to no existing file.

    Subclasses `FileNotFoundError` so existing callers that already catch
    `FileNotFoundError` (e.g., `tool_loader.load_tool`) keep working.
    """


def register_prompt_path(prompt_name: str, directory: Path) -> None:
    """Register a domain-owned directory for a single prompt.

    Registered paths are searched in registration order, before the legacy
    `backend/data/prompts/` location. A registered directory that does not
    contain the expected file falls back transparently to the next candidate.
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


def iter_prompt_candidate_paths(
    prompt_name: str, filename: str, legacy_dir: Path
) -> List[Path]:
    """Return candidate prompt file paths in priority order.

    Registered domain-owned directories come first, legacy last.
    """
    candidates: List[Path] = [
        directory / filename for directory in _prompt_dirs.get(prompt_name, [])
    ]
    candidates.append(legacy_dir / filename)
    return candidates


def iter_tool_candidate_paths(
    category: str, tool_name: str, legacy_dir: Path
) -> List[Path]:
    """Return candidate tool JSON file paths in priority order.

    Per-tool registrations win over per-category registrations, both of
    which win over the legacy `services/tools/<category>/` location.
    """
    filename = f"{tool_name}.json"
    candidates: List[Path] = [
        directory / filename
        for directory in _tool_file_dirs.get((category, tool_name), [])
    ]
    candidates.extend(
        directory / filename for directory in _tool_category_dirs.get(category, [])
    )
    candidates.append(legacy_dir / category / filename)
    return candidates


def iter_tool_category_dirs(category: str, legacy_dir: Path) -> List[Path]:
    """Return candidate directories for a tool category in priority order."""
    dirs: List[Path] = list(_tool_category_dirs.get(category, []))
    dirs.append(legacy_dir / category)
    return dirs


def registered_tool_categories() -> List[str]:
    """Return the tool categories that have any registered domain-owned dir."""
    return list(_tool_category_dirs.keys())


def resolve_prompt_path(prompt_name: str, filename: str, legacy_dir: Path) -> Path:
    """Return the first existing candidate prompt file, or raise.

    Internal resolver used by loaders that want an explicit miss signal. Public
    loader methods may still convert the raise into their existing contract
    (e.g., `get_prompt_config` returning `None`).
    """
    for candidate in iter_prompt_candidate_paths(prompt_name, filename, legacy_dir):
        if candidate.exists():
            return candidate
    raise AssetNotFoundError(
        f"Prompt asset not found: name={prompt_name!r}, filename={filename!r}. "
        f"Searched registered directories for {prompt_name!r} and legacy "
        f"directory {legacy_dir}."
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
        f"Searched registered per-file, per-category, and legacy directory "
        f"{legacy_dir / category}."
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


# Prompts that have moved to domain-owned homes (NBB-207B). The map lives here
# so it can be replayed after `_reset_for_tests()` during tests that need the
# production configuration restored.
#
# Key: prompt_name (the argument passed to `prompt_loader.get_prompt_config`).
# Value: directory path relative to `backend/app/`.
_PRODUCTION_PROMPT_PATHS: Dict[str, str] = {
    "pdf_extraction": "sources/pdf/prompts",
    "pptx_extraction": "sources/pptx/prompts",
    "image_extraction": "sources/image/prompts",
    "web_agent": "sources/link/prompts",
    "deep_research_agent": "sources/analysis/research/prompts",
    "website_agent": "studio/design/website/prompts",
    "blog_agent": "studio/documents/blog/prompts",
    "business_report_agent": "studio/documents/business_report/prompts",
    "prd_agent": "studio/documents/prd/prompts",
    "presentation_agent": "studio/documents/presentation/prompts",
}


# Tool categories that have moved to domain-owned homes (NBB-207C). Paired
# with `_PRODUCTION_PROMPT_PATHS` so both asset types replay through one
# function; the autouse reset fixture in
# `backend/tests/config/test_asset_registry.py` has a single replay hook.
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
    "website_agent": "studio/design/website/tools",
    "blog_agent": "studio/documents/blog/tools",
    "business_report_agent": "studio/documents/business_report/tools",
    "prd_agent": "studio/documents/prd/tools",
    "presentation_agent": "studio/documents/presentation/tools",
}


def register_production_asset_paths() -> None:
    """Register every domain-owned prompt/tool JSON path landed by NBB-207B/C.

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
