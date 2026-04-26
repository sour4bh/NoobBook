"""
Tests for the prompt/tool asset registry shims (NBB-207A).

These assert that:
- Existing prompt loader callers still resolve legacy prompt JSON paths
  unchanged.
- A registered domain-owned prompt directory resolves before the legacy path.
- Tool JSON resolves through the registry only after NBB-810.
- A fully missing asset raises a clear, identifiable error through the
  internal resolvers.
"""
import json
from pathlib import Path
from typing import Dict

import pytest

from app.config import asset_registry
from app.config.asset_registry import AssetNotFoundError
from app.config.prompt_loader import PromptLoader
from app.config.tool_loader import ToolLoader


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear registry mutations between tests.

    The production `prompt_loader` and `tool_loader` singletons share this
    module-level registry, so any leak would pollute other tests.
    """
    asset_registry._reset_for_tests()
    yield
    asset_registry._reset_for_tests()


def _write_prompt(dir_path: Path, filename: str, payload: Dict) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / filename
    path.write_text(json.dumps(payload))
    return path


def _write_tool(dir_path: Path, filename: str, name: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / filename
    path.write_text(
        json.dumps(
            {
                "name": name,
                "description": "test tool",
                "input_schema": {"type": "object", "properties": {}},
            }
        )
    )
    return path


def _loader_with_prompts_dir(tmp_path: Path) -> PromptLoader:
    loader = PromptLoader()
    loader.prompts_dir = tmp_path
    loader.projects_dir = tmp_path / "projects"
    loader.projects_dir.mkdir(parents=True, exist_ok=True)
    return loader


def _loader_with_tools_dir(tmp_path: Path) -> ToolLoader:
    loader = ToolLoader()
    loader.tools_dir = tmp_path
    return loader


# -- Prompt loader -----------------------------------------------------------


def test_prompt_legacy_path_resolves_unchanged(tmp_path):
    legacy = tmp_path / "prompts"
    _write_prompt(
        legacy,
        "memory_prompt.json",
        {
            "model": "claude-sonnet",
            "temperature": 0.0,
            "max_tokens": 1,
            "system_prompt": "legacy memory prompt",
        },
    )
    loader = _loader_with_prompts_dir(legacy)

    config = loader.get_prompt_config("memory")

    assert config is not None
    assert config["system_prompt"] == "legacy memory prompt"


def test_prompt_registered_path_wins_over_legacy(tmp_path):
    legacy = tmp_path / "prompts"
    owned = tmp_path / "chat" / "memory" / "prompts"
    _write_prompt(legacy, "memory_prompt.json", {"system_prompt": "legacy"})
    _write_prompt(owned, "memory_prompt.json", {"system_prompt": "owned"})
    asset_registry.register_prompt_path("memory", owned)

    loader = _loader_with_prompts_dir(legacy)

    config = loader.get_prompt_config("memory")

    assert config is not None
    assert config["system_prompt"] == "owned"


def test_prompt_registered_path_missing_file_falls_back_to_legacy(tmp_path):
    legacy = tmp_path / "prompts"
    owned = tmp_path / "chat" / "memory" / "prompts"
    owned.mkdir(parents=True, exist_ok=True)  # directory exists, file does not
    _write_prompt(legacy, "memory_prompt.json", {"system_prompt": "legacy"})
    asset_registry.register_prompt_path("memory", owned)

    loader = _loader_with_prompts_dir(legacy)

    config = loader.get_prompt_config("memory")

    assert config is not None
    assert config["system_prompt"] == "legacy"


def test_prompt_missing_everywhere_returns_none_via_public_api(tmp_path):
    legacy = tmp_path / "prompts"
    legacy.mkdir(parents=True, exist_ok=True)
    loader = _loader_with_prompts_dir(legacy)

    # `get_prompt_config` preserves its historical "soft miss" contract so
    # `model_loader.get_default_models_for_category` keeps working.
    assert loader.get_prompt_config("does_not_exist") is None


def test_prompt_missing_everywhere_raises_through_internal_resolver(tmp_path):
    legacy = tmp_path / "prompts"
    legacy.mkdir(parents=True, exist_ok=True)

    with pytest.raises(AssetNotFoundError) as err:
        asset_registry.resolve_prompt_path(
            "does_not_exist", "does_not_exist_prompt.json", legacy
        )

    # The error should clearly identify both the key and the legacy dir it
    # searched, so a human reading a traceback can tell why it missed.
    assert "does_not_exist" in str(err.value)
    assert str(legacy) in str(err.value)


# -- Tool loader -------------------------------------------------------------


def test_tool_registered_per_file_path_resolves(tmp_path):
    registry_root = tmp_path
    owned = tmp_path / "chat" / "memory" / "tools"
    _write_tool(owned, "memory_tool.json", "owned_memory")
    asset_registry.register_tool_path("chat_tools", "memory_tool", owned)

    loader = _loader_with_tools_dir(registry_root)

    tool = loader.load_tool("chat_tools", "memory_tool")

    assert tool["name"] == "owned_memory"


def test_tool_registered_per_file_missing_raises(tmp_path):
    registry_root = tmp_path
    owned = tmp_path / "chat" / "memory" / "tools"
    owned.mkdir(parents=True, exist_ok=True)  # dir exists, file does not
    asset_registry.register_tool_path("chat_tools", "memory_tool", owned)

    loader = _loader_with_tools_dir(registry_root)

    with pytest.raises(FileNotFoundError):
        loader.load_tool("chat_tools", "memory_tool")


def test_tool_registered_category_path_resolves(tmp_path):
    registry_root = tmp_path
    owned = tmp_path / "sources" / "pdf" / "tools"
    _write_tool(owned, "pdf_extraction.json", "owned_pdf")
    asset_registry.register_tool_category("pdf_tools", owned)

    loader = _loader_with_tools_dir(registry_root)

    assert loader.load_tool("pdf_tools", "pdf_extraction")["name"] == "owned_pdf"
    names = [t["name"] for t in loader.load_tools_from_category("pdf_tools")]
    assert names == ["owned_pdf"]


def test_tool_category_enumeration_uses_exact_file_registrations(tmp_path):
    """Mixed-owner directories should not leak unrelated tools into a category."""
    registry_root = tmp_path
    owned = tmp_path / "chat" / "memory" / "tools"
    _write_tool(owned, "memory_tool.json", "owned_memory")
    _write_tool(owned, "manage_memory_tool.json", "save_memory")
    asset_registry.register_tool_path("chat_tools", "memory_tool", owned)

    loader = _loader_with_tools_dir(registry_root)

    names = sorted(t["name"] for t in loader.load_tools_from_category("chat_tools"))
    assert names == ["owned_memory"]


def test_tool_missing_everywhere_raises_file_not_found(tmp_path):
    registry_root = tmp_path
    loader = _loader_with_tools_dir(registry_root)

    # Public API contract: missing tool raises FileNotFoundError.
    with pytest.raises(FileNotFoundError):
        loader.load_tool("pdf_tools", "does_not_exist")


def test_tool_missing_everywhere_raises_clear_error_through_resolver(tmp_path):
    registry_root = tmp_path

    with pytest.raises(AssetNotFoundError) as err:
        asset_registry.resolve_tool_path("pdf_tools", "does_not_exist", registry_root)

    msg = str(err.value)
    assert "pdf_tools" in msg
    assert "does_not_exist" in msg
    assert "registry-only" in msg


def test_public_register_helpers_exported_from_package():
    """Downstream tickets register via the package surface, not internals."""
    from app import config as config_pkg

    assert hasattr(config_pkg, "register_prompt_path")
    assert hasattr(config_pkg, "register_tool_path")
    assert hasattr(config_pkg, "register_tool_category")
    assert hasattr(config_pkg, "AssetNotFoundError")
