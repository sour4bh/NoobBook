"""Tests for provider-aware model configuration."""

from app.config.model import (
    AVAILABLE_MODELS,
    MODEL_CATEGORIES,
    get_current_settings,
    normalize_model_selection,
    workspace_model_overrides,
)


def test_model_catalog_exposes_provider_metadata() -> None:
    """NBB-1103: model ids are no longer implicitly Claude-only."""
    assert AVAILABLE_MODELS["claude-sonnet-4-6"]["provider"] == "anthropic"
    assert AVAILABLE_MODELS["gpt-5.1"]["provider"] == "openai"
    assert "responses" in AVAILABLE_MODELS["gpt-5.1"]["capabilities"]


def test_model_categories_include_default_provider() -> None:
    assert MODEL_CATEGORIES["chat"]["default_provider"] == "anthropic"


def test_model_selection_accepts_string_and_provider_shape() -> None:
    anthropic = normalize_model_selection("claude-haiku-4-5-20251001")
    openai = normalize_model_selection({"provider": "openai", "model": "gpt-5-mini"})

    assert anthropic is not None
    assert anthropic.provider == "anthropic"
    assert openai is not None
    assert openai.provider == "openai"


def test_model_selection_rejects_provider_model_mismatch() -> None:
    assert normalize_model_selection(
        {"provider": "anthropic", "model": "gpt-5.1"}
    ) is None


def test_current_settings_are_provider_aware_when_env_override_is_set(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CHAT_MODEL_OVERRIDE", "gpt-5-mini")

    settings = get_current_settings()

    assert settings["chat"] == {"provider": "openai", "model": "gpt-5-mini"}


def test_workspace_model_overrides_preserve_legacy_shape() -> None:
    settings = {
        "model_overrides": {
            "chat": "claude-haiku-4-5-20251001",
            "studio": "claude-opus-4-6",
        },
        "ai": {
            "models": {
                "studio": None,
                "query": {"provider": "openai", "model": "gpt-5-mini"},
            }
        },
    }

    assert workspace_model_overrides(settings) == {
        "chat": "claude-haiku-4-5-20251001",
        "studio": None,
        "query": {"provider": "openai", "model": "gpt-5-mini"},
    }
