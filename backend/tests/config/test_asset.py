"""
Tests for the tool asset registry.

These assert that:
- Tool specs resolve through the registry after NBB-1104.
"""
from pathlib import Path

import pytest

import app.config.asset as asset
from app.config.tool import ToolLoader


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear registry mutations between tests.

    The production `tool_loader` singleton reads this module-level registry, so
    any leak would pollute other tests.
    """
    asset._reset_for_tests()
    yield
    asset._reset_for_tests()
    asset.register_production_asset_paths()


def _write_tool(dir_path: Path, filename: str, name: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / "specs.py"
    if not path.exists():
        path.write_text(
            "from app.agents.runtime.tool import EmptyInput, LocalToolSpec\n\n"
            "TOOL_SPECS = []\n"
        )

    registry_name = Path(filename).stem
    with path.open("a") as handle:
        handle.write(
            "\nTOOL_SPECS.append(\n"
            "    LocalToolSpec(\n"
            f"        name={name!r},\n"
            "        description='test tool',\n"
            "        input_model=EmptyInput,\n"
            f"        metadata={{'registry_name': {registry_name!r}}},\n"
            "    )\n"
            ")\n"
        )
    return path


# -- Tool loader -------------------------------------------------------------


def test_tool_registered_per_file_path_resolves(tmp_path):
    owned = tmp_path / "chat" / "memory" / "tools"
    _write_tool(owned, "memory_tool.json", "owned_memory")
    asset.register_tool_path("chat_tools", "memory_tool", owned)

    loader = ToolLoader()

    tool = loader.load_tool_spec("chat_tools", "memory_tool")

    assert tool.name == "owned_memory"


def test_tool_registered_per_file_missing_raises(tmp_path):
    owned = tmp_path / "chat" / "memory" / "tools"
    owned.mkdir(parents=True, exist_ok=True)  # dir exists, file does not
    asset.register_tool_path("chat_tools", "memory_tool", owned)

    loader = ToolLoader()

    with pytest.raises(FileNotFoundError):
        loader.load_tool_spec("chat_tools", "memory_tool")


def test_tool_registered_category_path_resolves(tmp_path):
    owned = tmp_path / "sources" / "pdf" / "tools"
    _write_tool(owned, "pdf_extraction.json", "owned_pdf")
    asset.register_tool_category("pdf_tools", owned)

    loader = ToolLoader()

    assert loader.load_tool_spec("pdf_tools", "pdf_extraction").name == "owned_pdf"
    names = [t.name for t in loader.load_tool_specs_for_agent("pdf_tools")]
    assert names == ["owned_pdf"]


def test_tool_category_enumeration_uses_exact_file_registrations(tmp_path):
    """Mixed-owner directories should not leak unrelated tools into a category."""
    owned = tmp_path / "chat" / "memory" / "tools"
    _write_tool(owned, "memory_tool.json", "owned_memory")
    _write_tool(owned, "manage_memory_tool.json", "save_memory")
    asset.register_tool_path("chat_tools", "memory_tool", owned)

    loader = ToolLoader()

    names = sorted(t.name for t in loader.load_tool_specs_for_agent("chat_tools"))
    assert names == ["owned_memory"]


def test_tool_missing_everywhere_raises_file_not_found(tmp_path):
    loader = ToolLoader()

    # Public API contract: missing tool raises FileNotFoundError.
    with pytest.raises(FileNotFoundError):
        loader.load_tool_spec("pdf_tools", "does_not_exist")


def test_public_register_helpers_exported_from_package():
    """Downstream tickets register via the package surface, not internals."""
    from app import config as config_pkg

    assert hasattr(config_pkg, "register_tool_path")
    assert hasattr(config_pkg, "register_tool_category")
