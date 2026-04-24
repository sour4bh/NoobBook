"""
Tests for NBB-207B prompt ownership and prompt-loader compatibility.

These assert that the registered domain-owned prompt paths landed by this
ticket resolve end-to-end, legacy prompts still resolve from
`backend/data/prompts/`, and `/prompts/all` still sees every prompt regardless
of which directory it lives in. They use the real on-disk prompt files so the
expected production wiring is exercised, not a synthetic fixture.

The sibling `test_asset_registry.py` autouse fixture resets the registry
before and after each test; these tests explicitly re-invoke
`register_production_asset_paths()` after reset so they see the state a
running backend sees at startup.
"""
import pytest

from app.config import asset_registry
from app.config.prompt_loader import PromptLoader, prompt_loader


# Prompts moved to domain-owned homes in NBB-207B.
MOVED_PROMPTS = [
    ("pdf_extraction", "sources/pdf/prompts"),
    ("pptx_extraction", "sources/pptx/prompts"),
    ("image_extraction", "sources/image/prompts"),
    ("web_agent", "sources/link/prompts"),
    ("deep_research_agent", "sources/analysis/research/prompts"),
]

# A handful of prompts intentionally left in the legacy directory. Each has a
# downstream ticket that will rehome it once the owning-domain skeleton lands.
LEGACY_PROMPTS = [
    "memory",
    "chat_naming",
    "summary",
    "csv_processor",
    "default",
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
    """Build a PromptLoader pointed at the real `backend/data/prompts/` dir.

    The production singleton is pre-wired with `Config.DATA_DIR / "prompts"`,
    which is the legacy path these tests rely on for the still-legacy prompts.
    A fresh instance picks up the same directory because `PromptLoader`'s
    constructor reads `Config.DATA_DIR`, and restores any test mutation to
    `prompts_dir` on the shared singleton.
    """
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
    # Confirm the resolver actually used the registered dir, not the legacy
    # dir: the legacy copy is gone, so any legacy-only path would miss.
    assert not (loader.prompts_dir / f"{prompt_name}_prompt.json").exists()


@pytest.mark.parametrize("prompt_name", LEGACY_PROMPTS)
def test_legacy_prompt_resolves_from_data_prompts(prompt_name: str) -> None:
    """Prompts still in `backend/data/prompts/` must keep resolving.

    Domain skeletons for the owning features (chat, studio, csv analysis)
    have not landed at base commit 2bf0b55, so these prompts are explicitly
    `deferred-to-later-ticket` in the NBB-207B ownership map.
    """
    loader = _fresh_loader()

    config = loader.get_prompt_config(prompt_name)

    assert config is not None, f"legacy prompt {prompt_name!r} did not resolve"
    assert (loader.prompts_dir / f"{prompt_name}_prompt.json").exists()


def test_list_all_prompts_returns_every_prompt_across_locations() -> None:
    """`/prompts/all` must still return every prompt file.

    Without the `list_all_prompts` fix, moved prompts silently disappear
    from the settings UI. The current prompt count should be the union of
    the legacy directory and every registered domain directory, with no
    duplicates.
    """
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
    for prompt_name in LEGACY_PROMPTS:
        assert f"{prompt_name}_prompt.json" in filenames, (
            f"legacy prompt {prompt_name!r} missing from list_all_prompts"
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
