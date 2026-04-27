"""
Tests for NBB-207B prompt ownership and prompt-loader compatibility.

These assert that registered domain-owned prompt paths resolve end-to-end and
`/prompts/all` sees every registered prompt. They use the real on-disk prompt
files so the expected production wiring is exercised, not a synthetic fixture.

The sibling `test_asset_registry.py` autouse fixture resets the registry
before and after each test; these tests explicitly re-invoke
`register_production_asset_paths()` after reset so they see the state a
running backend sees at startup.
"""
import pytest

from app.config import asset_registry
from app.config.prompt_loader import PromptLoader, prompt_loader


# Prompts moved to domain-owned homes.
MOVED_PROMPTS = [
    ("default", "chat/prompts"),
    ("chat_naming", "chat/prompts"),
    ("memory", "chat/memory/prompts"),
    ("summary", "sources/prompts"),
    ("csv_analyzer_agent", "sources/analysis/csv/prompts"),
    ("csv_processor", "sources/analysis/csv/prompts"),
    ("database_analyzer_agent", "sources/analysis/database/prompts"),
    ("freshdesk_analyzer_agent", "sources/analysis/freshdesk/prompts"),
    ("pdf_extraction", "sources/pdf/prompts"),
    ("pptx_extraction", "sources/pptx/prompts"),
    ("image_extraction", "sources/image/prompts"),
    ("web_agent", "sources/link/prompts"),
    ("deep_research_agent", "sources/analysis/research/prompts"),
]

@pytest.fixture(autouse=True)
def _restore_production_registry():
    """Replay production registrations after the sibling reset fixture runs.

    The autouse fixture in `test_asset_registry.py` calls
    `_reset_for_tests()` between every test in this directory, including this
    file. Production registration happens exactly once at `app.config`
    import, so once the reset fires the real paths are gone for the rest of
    the session. Replay them here to restore the state under test.
    """
    asset_registry._reset_for_tests()
    asset_registry.register_production_asset_paths()
    yield
    asset_registry._reset_for_tests()


def _fresh_loader() -> PromptLoader:
    """Build a PromptLoader with production registry state."""
    return PromptLoader()


@pytest.mark.parametrize(
    "prompt_name,relative_dir",
    MOVED_PROMPTS,
    ids=[name for name, _ in MOVED_PROMPTS],
)
def test_moved_prompt_resolves_from_registered_domain_path(
    prompt_name: str, relative_dir: str
) -> None:
    """Each NBB-207B move must resolve via the registered domain dir.

    Failure here means the prompt file moved but the registry pointer did
    not, or vice versa — either way, production `get_prompt_config` would
    return `None`.
    """
    loader = _fresh_loader()

    config = loader.get_prompt_config(prompt_name)

    assert config is not None, f"registered prompt {prompt_name!r} did not resolve"
    assert "system_prompt" in config


def test_list_all_prompts_returns_every_prompt_across_locations() -> None:
    """`/prompts/all` must still return every registered prompt file."""
    loader = _fresh_loader()

    prompts = loader.list_all_prompts()

    filenames = [p["filename"] for p in prompts]
    assert len(filenames) == len(set(filenames)), (
        f"list_all_prompts returned duplicates: {filenames}"
    )
    for prompt_name, _ in MOVED_PROMPTS:
        assert f"{prompt_name}_prompt.json" in filenames, (
            f"registered prompt {prompt_name!r} missing from list_all_prompts"
        )


def test_singleton_sees_registered_paths() -> None:
    """The `prompt_loader` singleton must see production registrations.

    Services cache `prompt_loader.get_prompt_config(...)` results; this
    covers the path that real runtime callers take, not a freshly built
    `PromptLoader`.
    """
    config = prompt_loader.get_prompt_config("pdf_extraction")

    assert config is not None
    assert "system_prompt" in config
