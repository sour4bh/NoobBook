"""
Provider-aware model configuration for prompt categories.

Every registered prompt has a baked-in provider/model pair. Workspace admins
can override the model per category without editing domain-owned prompt files.
Anthropic remains the default provider; OpenAI entries are present so the
runtime can select Responses models once the OpenAI adapter lands.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Literal, Optional, cast

from pydantic import Field

from app.base.contracts import ContractModel


ModelProvider = Literal["anthropic", "openai"]
PROVIDER_API_KEYS: Dict[ModelProvider, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class ModelPricing(ContractModel):
    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: Optional[float] = None


class ModelInfo(ContractModel):
    id: str
    provider: ModelProvider
    name: str
    description: str
    pricing: ModelPricing
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    capabilities: list[str] = Field(default_factory=list)


class ModelCategory(ContractModel):
    id: str
    label: str
    description: str
    env_var: str
    default_provider: ModelProvider = "anthropic"


class ModelSelection(ContractModel):
    provider: ModelProvider
    model: str


class PromptModel(str):
    """String model id that carries prompt/provider metadata."""

    def __new__(
        cls,
        value: str,
        prompt_name: Optional[str] = None,
        provider: Optional[ModelProvider] = None,
    ):
        instance = str.__new__(cls, value)
        instance.prompt_name = prompt_name
        instance.provider = provider
        return instance


_AVAILABLE_MODEL_SPECS: Dict[str, ModelInfo] = {
    "claude-haiku-4-5-20251001": ModelInfo(
        id="claude-haiku-4-5-20251001",
        provider="anthropic",
        name="Claude Haiku 4.5",
        description="Fastest and cheapest. Best for simple or high-volume tasks.",
        pricing=ModelPricing(input_per_mtok=1.0, output_per_mtok=5.0),
        capabilities=["messages", "tools", "vision"],
    ),
    "claude-sonnet-4-6": ModelInfo(
        id="claude-sonnet-4-6",
        provider="anthropic",
        name="Claude Sonnet 4.6",
        description="Balanced speed and quality. Default for most tasks.",
        pricing=ModelPricing(input_per_mtok=3.0, output_per_mtok=15.0),
        capabilities=["messages", "tools", "vision"],
    ),
    "claude-sonnet-4-5-20250929": ModelInfo(
        id="claude-sonnet-4-5-20250929",
        provider="anthropic",
        name="Claude Sonnet 4.5",
        description="Previous Sonnet model retained for direct provider callers and tests.",
        pricing=ModelPricing(input_per_mtok=3.0, output_per_mtok=15.0),
        capabilities=["messages", "tools", "vision"],
    ),
    "claude-opus-4-6": ModelInfo(
        id="claude-opus-4-6",
        provider="anthropic",
        name="Claude Opus 4.6",
        description="Most capable. Best for complex reasoning and high-quality generation.",
        pricing=ModelPricing(input_per_mtok=5.0, output_per_mtok=25.0),
        capabilities=["messages", "tools", "vision"],
    ),
    "gpt-5.1": ModelInfo(
        id="gpt-5.1",
        provider="openai",
        name="GPT-5.1",
        description="OpenAI flagship Responses model for coding and agentic tasks.",
        pricing=ModelPricing(
            input_per_mtok=1.25,
            cached_input_per_mtok=0.125,
            output_per_mtok=10.0,
        ),
        context_window=400000,
        max_output_tokens=128000,
        capabilities=["responses", "tools", "structured_output", "reasoning"],
    ),
    "gpt-5-mini": ModelInfo(
        id="gpt-5-mini",
        provider="openai",
        name="GPT-5 mini",
        description="Faster OpenAI Responses model for well-defined tasks.",
        pricing=ModelPricing(
            input_per_mtok=0.25,
            cached_input_per_mtok=0.025,
            output_per_mtok=2.0,
        ),
        capabilities=["responses", "tools", "structured_output", "reasoning"],
    ),
}


AVAILABLE_MODELS: Dict[str, Dict[str, Any]] = {
    model_id: spec.model_dump(mode="json")
    for model_id, spec in _AVAILABLE_MODEL_SPECS.items()
}


_MODEL_CATEGORY_SPECS: Dict[str, ModelCategory] = {
    "chat": ModelCategory(
        id="chat",
        label="Chat",
        description="Main conversation, auto-naming, and memory updates.",
        env_var="CHAT_MODEL_OVERRIDE",
    ),
    "studio": ModelCategory(
        id="studio",
        label="Studio",
        description="Audio, video, presentations, websites, emails, mind maps, quizzes, and other generation.",
        env_var="STUDIO_MODEL_OVERRIDE",
    ),
    "query": ModelCategory(
        id="query",
        label="Query Agents",
        description="Database, CSV, and Freshdesk analysis agents.",
        env_var="QUERY_MODEL_OVERRIDE",
    ),
    "extraction": ModelCategory(
        id="extraction",
        label="Source Extraction",
        description="Background processing: PDF, PPTX, image, CSV extraction and source summaries.",
        env_var="EXTRACTION_MODEL_OVERRIDE",
    ),
}


MODEL_CATEGORIES: Dict[str, Dict[str, Any]] = {
    category_id: spec.model_dump(mode="json")
    for category_id, spec in _MODEL_CATEGORY_SPECS.items()
}


# Maps prompt names (without the "_prompt" suffix) to their category.
# Prompts not listed here (web_agent, deep_research_agent) keep their prompt
# file's provider/model pair and are unaffected by admin overrides.
PROMPT_TO_CATEGORY: Dict[str, str] = {
    # Chat
    "default": "chat",
    "chat_naming": "chat",
    "memory": "chat",
    # Studio
    "audio_script": "studio",
    "video": "studio",
    "mind_map": "studio",
    "quiz": "studio",
    "flash_cards": "studio",
    "social_posts": "studio",
    "infographic": "studio",
    "flow_diagram": "studio",
    "ad_creative": "studio",
    "component_agent": "studio",
    "wireframe_agent": "studio",
    "wireframe": "studio",
    "website_agent": "studio",
    "presentation_agent": "studio",
    "email_agent": "studio",
    "blog_agent": "studio",
    "prd_agent": "studio",
    "business_report_agent": "studio",
    "marketing_strategy_agent": "studio",
    # Query agents
    "database_analyzer_agent": "query",
    "csv_analyzer_agent": "query",
    "freshdesk_analyzer_agent": "query",
    # Source extraction
    "pdf_extraction": "extraction",
    "pptx_extraction": "extraction",
    "image_extraction": "extraction",
    "csv_processor": "extraction",
    "summary": "extraction",
}


def get_model_info(model_id: str) -> Optional[ModelInfo]:
    return _AVAILABLE_MODEL_SPECS.get(model_id)


def provider_for_model(model_id: str) -> Optional[ModelProvider]:
    info = get_model_info(model_id)
    return info.provider if info else None


def normalize_model_selection(value: Any) -> Optional[ModelSelection]:
    """Normalize persisted/API/env model values into provider-aware shape."""
    if value in (None, ""):
        return None

    if isinstance(value, str):
        info = get_model_info(value)
        if not info:
            return None
        return ModelSelection(provider=info.provider, model=value)

    if isinstance(value, dict):
        model = value.get("model")
        provider = value.get("provider")
        if not isinstance(model, str):
            return None
        info = get_model_info(model)
        if not info:
            return None
        if provider is not None and provider != info.provider:
            return None
        return ModelSelection(provider=info.provider, model=model)

    return None


def workspace_model_overrides(settings: Any) -> Dict[str, Any]:
    """Return model overrides from current settings, preserving legacy shape.

    NBB-011 moved workspace model overrides from the old top-level
    ``settings.model_overrides`` map to ``settings.ai.models``. Runtime reads
    both so existing workspaces keep their choices until the next admin save
    writes the normalized shape.
    """
    if not isinstance(settings, dict):
        return {}

    overrides: Dict[str, Any] = {}
    settings_map = cast(Dict[str, Any], settings)
    legacy = settings_map.get("model_overrides")
    if isinstance(legacy, dict):
        overrides.update(cast(Dict[str, Any], legacy))

    ai_settings = settings_map.get("ai")
    if isinstance(ai_settings, dict):
        ai_settings_map = cast(Dict[str, Any], ai_settings)
        ai_legacy = ai_settings_map.get("model_overrides")
        if isinstance(ai_legacy, dict):
            overrides.update(cast(Dict[str, Any], ai_legacy))
        current = ai_settings_map.get("models")
        if isinstance(current, dict):
            overrides.update(cast(Dict[str, Any], current))

    return overrides


def get_category_model_selection(category: str) -> Optional[ModelSelection]:
    """Read a category override from the environment."""
    category_info = MODEL_CATEGORIES.get(category)
    if not category_info:
        return None
    value = os.environ.get(category_info["env_var"], "").strip()
    selection = normalize_model_selection(value)
    if selection and not is_provider_configured(selection.provider):
        return None
    return selection


def get_category_override(category: str) -> Optional[str]:
    """Return the override model id for legacy string callers."""
    selection = get_category_model_selection(category)
    return selection.model if selection else None


def get_workspace_category_model_selection(
    category: str,
    project_id: Optional[str],
) -> Optional[ModelSelection]:
    """Read a workspace model override through the current project."""
    if not project_id:
        return None
    try:
        from app.config.secret import get_project_settings

        settings = get_project_settings(project_id)
    except Exception:
        return None
    overrides = workspace_model_overrides(settings)
    selection = normalize_model_selection(overrides.get(category))
    if selection and not is_provider_configured(selection.provider, project_id=project_id):
        return None
    return selection


def get_workspace_category_override(
    category: str,
    project_id: Optional[str],
) -> Optional[str]:
    """Return the workspace override model id for legacy string callers."""
    selection = get_workspace_category_model_selection(category, project_id)
    return selection.model if selection else None


def get_model_selection_for_prompt(prompt_name: str) -> Optional[ModelSelection]:
    """
    Given a prompt name (e.g. "default", "presentation_agent"), return the
    admin-configured override selection for its category, or None.
    """
    category = PROMPT_TO_CATEGORY.get(prompt_name)
    if not category:
        return None
    return get_category_model_selection(category)


def get_model_override_for_prompt(prompt_name: str) -> Optional[str]:
    """Return the override model id for legacy string callers."""
    selection = get_model_selection_for_prompt(prompt_name)
    return selection.model if selection else None


def resolve_model_selection_for_project(
    model: str,
    project_id: Optional[str],
) -> ModelSelection:
    """Resolve a prompt model against workspace settings when possible."""
    prompt_name = getattr(model, "prompt_name", None)
    if prompt_name:
        category = PROMPT_TO_CATEGORY.get(prompt_name)
        if category:
            override = get_workspace_category_model_selection(category, project_id)
            if override:
                _require_provider_configured(override.provider, project_id=project_id)
                return override

    selection = normalize_model_selection(
        {
            "provider": getattr(model, "provider", None),
            "model": str(model),
        }
    )
    if selection:
        _require_provider_configured(selection.provider, project_id=project_id)
        return selection
    raise ValueError(f"Unknown model selection for {model!r}")


def resolve_model_for_project(model: str, project_id: Optional[str]) -> str:
    """Resolve a PromptModel against workspace settings when possible."""
    return resolve_model_selection_for_project(model, project_id).model


def get_current_settings() -> Dict[str, Optional[Dict[str, str]]]:
    """
    Return the current override for every category.

    A value of None means "Default" (the prompt's own provider/model is used).
    """
    settings: Dict[str, Optional[Dict[str, str]]] = {}
    for category in MODEL_CATEGORIES:
        selection = get_category_model_selection(category)
        settings[category] = selection.model_dump(mode="json") if selection else None
    return settings


def is_provider_configured(
    provider: ModelProvider,
    *,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    """Return whether a provider has a usable workspace or env API key."""
    key = PROVIDER_API_KEYS[provider]
    try:
        from app.config.secret import get_secret

        return bool(
            get_secret(
                key,
                workspace_id=workspace_id,
                project_id=project_id,
                env_fallback=True,
            )
        )
    except Exception:
        return bool(os.getenv(key))


def _require_provider_configured(
    provider: ModelProvider,
    *,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    if not is_provider_configured(
        provider,
        workspace_id=workspace_id,
        project_id=project_id,
    ):
        key = PROVIDER_API_KEYS[provider]
        raise ValueError(f"{provider} provider is not configured; set {key} first")


def get_configured_providers(
    *,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[ModelProvider]:
    """Return configured model providers in stable display order."""
    return [
        provider
        for provider in PROVIDER_API_KEYS
        if is_provider_configured(
            provider,
            workspace_id=workspace_id,
            project_id=project_id,
        )
    ]


def get_available_models(
    *,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """Return models whose provider has a configured key."""
    providers = set(
        get_configured_providers(
            workspace_id=workspace_id,
            project_id=project_id,
        )
    )
    return [
        model
        for model in AVAILABLE_MODELS.values()
        if model.get("provider") in providers
    ]


def get_default_models_for_category(category: str) -> Dict[str, list]:
    """
    Return {model_id: [prompt_names]} showing each prompt's baked-in model.
    """
    from app.config.prompt import list_prompt_specs

    breakdown: Dict[str, list] = {}
    for spec in list_prompt_specs():
        if spec.model_category != category:
            continue
        breakdown.setdefault(spec.default_model, []).append(spec.name)
    for prompts in breakdown.values():
        prompts.sort()
    return breakdown


def get_all_default_models() -> Dict[str, Dict[str, list]]:
    """Return {category_id: {model_id: [prompt_names]}} for every category."""
    return {cat_id: get_default_models_for_category(cat_id) for cat_id in MODEL_CATEGORIES}
