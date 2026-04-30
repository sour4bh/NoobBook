"""
Tests for typed prompt ownership and public prompt serialization.

These assert that domain-owned prompt.py modules resolve end-to-end and
`/prompts/all` sees every prompt spec. They use the real on-disk prompt specs
so the expected production wiring is exercised, not a synthetic fixture.

Prompt discovery is independent of the tool asset registry, so these tests
exercise the production discovery path directly.
"""
from app.config.prompt import (
    PromptSpec,
    get_prompt_spec,
    list_prompt_specs,
    list_public_prompt_configs,
    render_prompt,
)


PROMPT_NAMES = [
    "default",
    "chat_naming",
    "memory",
    "summary",
    "csv_analyzer_agent",
    "csv_processor",
    "database_analyzer_agent",
    "freshdesk_analyzer_agent",
    "pdf_extraction",
    "pptx_extraction",
    "image_extraction",
    "web_agent",
    "deep_research_agent",
]


def test_prompt_modules_discover_expected_specs() -> None:
    names = {spec.name for spec in list_prompt_specs()}

    for prompt_name in PROMPT_NAMES:
        assert prompt_name in names, (
            f"prompt spec {prompt_name!r} missing from prompt discovery"
        )


def test_prompt_specs_resolve_by_name(
    prompt_name: str = "memory",
) -> None:
    spec = get_prompt_spec(prompt_name)

    assert spec is not None, f"registered prompt {prompt_name!r} did not resolve"
    assert spec.system_prompt


def test_list_all_prompts_returns_every_prompt_across_locations() -> None:
    """`/prompts/all` must still return every discovered prompt spec."""
    prompts = list_public_prompt_configs()

    filenames = [p["filename"] for p in prompts]
    assert len(filenames) == len(set(filenames)), (
        f"list_all_prompts returned duplicates: {filenames}"
    )
    for prompt_name in PROMPT_NAMES:
        assert f"{prompt_name}.py" in filenames, (
            f"registered prompt {prompt_name!r} missing from list_all_prompts"
        )


def test_public_prompt_serialization_uses_prompt_specs() -> None:
    """Prompt routes serialize typed PromptSpecs, not prompt JSON files."""
    configs = {
        config["name"]: config
        for config in list_public_prompt_configs()
    }

    config = configs["pdf_extraction"]

    assert config["source"] == "python"
    assert config["filename"] == "pdf_extraction.py"
    assert "system_prompt" in config


def test_every_discovered_prompt_is_a_prompt_spec() -> None:
    """NBB-1113: prompt.py modules expose typed prompt specs."""
    specs = list_prompt_specs()

    assert specs
    for spec in specs:
        assert isinstance(spec, PromptSpec)
        assert spec.provider == "anthropic"
        assert spec.model.startswith("claude-")


def test_prompt_spec_exposes_provider_aware_defaults() -> None:
    """Runtime callers read provider/model defaults from the typed spec."""
    spec = get_prompt_spec("pdf_extraction")

    assert spec is not None
    assert spec.provider == "anthropic"
    assert spec.model == "claude-haiku-4-5-20251001"


def test_render_prompt_formats_user_message_context() -> None:
    rendered = render_prompt(
        "memory",
        {
            "memory_type": "project",
            "current_memory": "(empty)",
            "new_memory": "Prefers concise answers",
            "reason": "User requested it",
        },
    )

    assert rendered.name == "memory"
    assert rendered.provider == "anthropic"
    assert "Prefers concise answers" in (rendered.user_message or "")


def test_render_prompt_treats_system_prompt_examples_as_literal_text() -> None:
    """Literal JSON/CSS/Mermaid braces in system prompts are not templates."""
    rendered = render_prompt(
        "flow_diagram",
        {
            "direction": "show the process",
            "content": "Start, decide, act.",
        },
    )

    assert "B{Decision?}" in rendered.system_prompt
    assert "USER ||--o{ ORDER : places" in rendered.system_prompt
    assert "Direction from user: show the process" in (rendered.user_message or "")
