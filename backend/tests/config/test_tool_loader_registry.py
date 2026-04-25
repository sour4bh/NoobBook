"""
Tests for NBB-207C tool-schema ownership and tool-loader compatibility.

These assert that the registered domain-owned tool paths landed by this
ticket resolve end-to-end, tools still in `backend/app/services/tools/` keep
resolving from the legacy dir, and both `load_tool` and `load_tools_for_agent`
see the registered paths via the production singleton.

The sibling `test_asset_registry.py` autouse fixture resets the registry
before and after each test; these tests explicitly re-invoke
`register_production_asset_paths()` after reset so they see the state a
running backend sees at startup. This mirrors the pattern established by
`test_prompt_loader_registry.py` for NBB-207B.
"""
from typing import List, Tuple

import pytest

from app.config import asset_registry
from app.config.tool_loader import ToolLoader, tool_loader


# Tool families moved to domain-owned homes in NBB-207C. Each entry carries the
# loader category key (unchanged; consumers keep passing it), the expected
# relative destination dir, the client-tool stems (loadable via
# `load_tool`), and the full tool-stem list (what
# `load_tools_from_category` returns, including server tools that carry no
# `input_schema` and therefore cannot be loaded via the validating
# `load_tool`).
MOVED_TOOL_FAMILIES: List[Tuple[str, str, List[str], List[str]]] = [
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
]


# Categories explicitly left under `backend/app/services/tools/` for downstream
# tickets. These must still resolve from the legacy dir to prove the registry
# has not accidentally claimed ownership before the owning skeleton exists.
LEGACY_TOOL_CATEGORIES: List[str] = [
    "chat_tools",
    "memory_tools",
    # studio_tools removed: all 5 JSONs (flash_cards/mind_map/quiz/
    # read_source_content/write_script_section + flow_diagram/wireframe in
    # NBB-506) migrated to studio domain via _PRODUCTION_TOOL_FILE_PATHS.
    # Legacy dir is now empty (NBB-507).
    "analysis_agent",
    "csv_tool",
    "database_agent",
    "freshdesk_agent",
]


@pytest.fixture(autouse=True)
def _restore_production_registry():
    """Replay production registrations after the sibling reset fixture runs.

    The autouse fixture in `test_asset_registry.py` calls
    `_reset_for_tests()` between every test in this directory. Production
    registration happens exactly once at `app.config` import, so once the
    reset fires the real paths are gone for the rest of the session. Replay
    them here to restore the state under test.
    """
    asset_registry._reset_for_tests()
    asset_registry.register_production_asset_paths()
    yield
    asset_registry._reset_for_tests()


def _fresh_loader() -> ToolLoader:
    """Build a ToolLoader pointed at `backend/app/services/tools/`.

    The production singleton reads the same directory; a fresh instance
    picks it up via `Path(__file__).parent.parent / "services" / "tools"`
    in `ToolLoader.__init__`.
    """
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

    # Confirm the resolver actually used the registered dir: the legacy
    # directory for this family is now empty, so a legacy-only lookup would
    # miss.
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


@pytest.mark.parametrize("category", LEGACY_TOOL_CATEGORIES)
def test_legacy_tool_category_directory_still_resolves(category: str) -> None:
    """Categories still under `services/tools/` must keep resolving.

    Downstream tickets (chat, studio, analysis slices) will rehome these
    once their owning-domain skeletons land. Until then the legacy path is
    the only valid source.

    Existence is the contract: the directory must be discoverable under the
    legacy tools dir and contain at least one JSON file. We intentionally
    do not call `load_tools_from_category` here because unrelated preexisting
    empty/placeholder JSONs (e.g., `chat_tools/compact_tool.json`) would
    raise on decode and mask the NBB-207C-specific signal.
    """
    loader = _fresh_loader()
    legacy_dir = loader.tools_dir / category

    assert legacy_dir.is_dir(), (
        f"legacy category dir {legacy_dir} missing after NBB-207C"
    )
    tool_files = list(legacy_dir.glob("*.json"))
    assert tool_files, (
        f"legacy category {category!r} has no JSON files after NBB-207C"
    )


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
