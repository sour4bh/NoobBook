"""Typed prompt contracts and rendering.

Built-in prompts are app code, not runtime JSON assets. Owning domains expose
``PROMPT`` or ``PROMPTS`` from ``prompt.py`` modules, while this config module
discovers those specs, validates model metadata, applies model overrides, and
renders final prompt text for runtime callers.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from string import Formatter
from typing import Any, Iterable, Mapping, Optional

from pydantic import Field, model_validator

from app.base.contracts import ContractModel
from app.config.model import (
    ModelProvider,
    PromptModel,
    get_model_selection_for_prompt,
    normalize_model_selection,
    resolve_model_selection_for_project,
)
from app.config.runtime import Config

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parents[1]


class PromptTemplate(ContractModel):
    """Format string owned by a prompt spec."""

    text: str

    def render(self, context: Mapping[str, Any] | None = None) -> str:
        required = self.required_fields()
        if not required:
            return self.text
        if not context:
            raise ValueError(
                f"prompt template requires context fields: {sorted(required)}"
            )
        missing = required - set(context)
        if missing:
            raise ValueError(
                f"prompt template missing context fields: {sorted(missing)}"
            )
        return self.text.format(**dict(context))

    def required_fields(self) -> set[str]:
        fields: set[str] = set()
        for _literal, field_name, _format_spec, _conversion in Formatter().parse(
            self.text
        ):
            if field_name:
                fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
        return fields


class PromptSection(ContractModel):
    """Optional section appended during prompt composition."""

    title: str | None = None
    body: str

    def render(self) -> str:
        if self.title:
            return f"{self.title}\n{self.body}"
        return self.body


class PromptSpec(ContractModel):
    """Domain-owned built-in prompt definition."""

    name: str
    description: str = ""
    default_provider: ModelProvider = "anthropic"
    default_model: str
    model_category: str | None = None
    max_tokens: int = Field(gt=0)
    temperature: float = Field(ge=0.0)
    system_prompt: str
    user_message: str | None = None
    user_message_template: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provider_model_pair(self) -> "PromptSpec":
        selection = normalize_model_selection(
            {"provider": self.default_provider, "model": self.default_model}
        )
        if selection is None:
            raise ValueError(
                f"unknown provider/model pair: "
                f"{self.default_provider}/{self.default_model}"
            )
        return self

    def system_template(self) -> PromptTemplate:
        return PromptTemplate(text=self.system_prompt)

    @property
    def provider(self) -> ModelProvider:
        return self.default_provider

    @property
    def model(self) -> str:
        return self.default_model

    def user_template(self) -> PromptTemplate | None:
        text = self.user_message_template or self.user_message
        if text is None:
            return None
        return PromptTemplate(text=text)

    def default_config(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "provider": self.default_provider,
            "model": self.default_model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system_prompt": self.system_prompt,
        }
        if self.version is not None:
            data["version"] = self.version
        if self.user_message is not None:
            data["user_message"] = self.user_message
        if self.user_message_template is not None:
            data["user_message_template"] = self.user_message_template
        data.update(self.metadata)
        return data

    def public_config(self) -> dict[str, Any]:
        data = self.default_config()
        # Kept for the existing settings UI field while the source is Python.
        data["filename"] = f"{self.name}.py"
        data["source"] = "python"
        return data


class RenderedPrompt(ContractModel):
    """Final prompt payload ready for a runtime request."""

    name: str
    provider: ModelProvider
    model: str
    max_tokens: int
    temperature: float
    system_prompt: str
    user_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


_prompt_specs: dict[str, PromptSpec] | None = None


def _context_data(context: ContractModel | Mapping[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {}
    if isinstance(context, ContractModel):
        return context.model_dump(mode="python")
    if isinstance(context, Mapping):
        return dict(context)
    raise TypeError("prompt render context must be a Pydantic model or mapping")


def _iter_prompt_module_paths() -> Iterable[Path]:
    for path in sorted(APP_DIR.rglob("prompt.py")):
        if path == Path(__file__).resolve():
            continue
        yield path


def _load_prompt_module(path: Path) -> Any:
    rel = path.relative_to(APP_DIR).with_suffix("")
    module_name = "_noobbook_prompt_" + "_".join(rel.parts)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load prompt module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _coerce_module_specs(module_label: str, value: Any) -> list[PromptSpec]:
    if isinstance(value, PromptSpec):
        return [value]
    if isinstance(value, tuple):
        specs = list(value)
    elif isinstance(value, list):
        specs = value
    else:
        raise TypeError(
            f"{module_label} must export PROMPT or PROMPTS as PromptSpec values"
        )
    if not all(isinstance(spec, PromptSpec) for spec in specs):
        raise TypeError(f"{module_label} exported a non-PromptSpec prompt")
    return specs


def _discover_prompt_specs() -> dict[str, PromptSpec]:
    specs: dict[str, PromptSpec] = {}
    for path in _iter_prompt_module_paths():
        module_label = str(path.relative_to(APP_DIR))
        module = _load_prompt_module(path)
        exported = None
        if hasattr(module, "PROMPT"):
            exported = getattr(module, "PROMPT")
        if hasattr(module, "PROMPTS"):
            prompts = getattr(module, "PROMPTS")
            exported = prompts if exported is None else (exported, *prompts)
        if exported is None:
            raise ValueError(
                f"{module_label} is named prompt.py but exports no PROMPT/PROMPTS"
            )
        for spec in _coerce_module_specs(module_label, exported):
            if spec.name in specs:
                raise ValueError(f"duplicate prompt name: {spec.name}")
            specs[spec.name] = spec
    return specs


def _all_prompt_specs() -> dict[str, PromptSpec]:
    global _prompt_specs
    if _prompt_specs is None:
        _prompt_specs = _discover_prompt_specs()
    return _prompt_specs


def reset_prompt_cache_for_tests() -> None:
    """Clear discovered prompt specs after test-time module mutations."""

    global _prompt_specs
    _prompt_specs = None


def get_prompt_spec(prompt_name: str) -> PromptSpec | None:
    return _all_prompt_specs().get(prompt_name)


def list_prompt_specs() -> list[PromptSpec]:
    return [spec for _name, spec in sorted(_all_prompt_specs().items())]


def _compose_system_prompt(
    base: str,
    sections: Iterable[str | PromptSection],
) -> str:
    rendered = [base]
    for section in sections:
        if isinstance(section, PromptSection):
            rendered.append(section.render())
        else:
            rendered.append(str(section))
    return "\n\n".join(part for part in rendered if part)


def render_prompt(
    prompt_name: str,
    context: ContractModel | Mapping[str, Any] | None = None,
    *,
    project_id: str | None = None,
    system_override: str | None = None,
    extra_sections: Iterable[str | PromptSection] = (),
) -> RenderedPrompt:
    """Render a named built-in prompt through the central prompt contract."""

    spec = get_prompt_spec(prompt_name)
    if spec is None:
        raise FileNotFoundError(f"Prompt spec not found: {prompt_name}")

    values = _context_data(context)
    # System prompts are long-lived instruction documents. Many include literal
    # JSON, CSS, or Mermaid examples, so only user-message templates are treated
    # as format strings unless a future prompt explicitly adds a separate
    # system-template contract.
    system = system_override or spec.system_prompt
    system = _compose_system_prompt(system, extra_sections)

    user_template = spec.user_template()
    user_message = user_template.render(values) if user_template else None

    if project_id:
        model_value = PromptModel(
            spec.default_model,
            prompt_name=spec.name,
            provider=spec.default_provider,
        )
        selection = resolve_model_selection_for_project(model_value, project_id)
    else:
        selection = get_model_selection_for_prompt(spec.name) or normalize_model_selection(
            {"provider": spec.default_provider, "model": spec.default_model}
        )
        if selection is None:
            raise ValueError(
                f"unknown provider/model pair: "
                f"{spec.default_provider}/{spec.default_model}"
            )

    return RenderedPrompt(
        name=spec.name,
        provider=selection.provider,
        model=selection.model,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
        system_prompt=system,
        user_message=user_message,
        metadata=dict(spec.metadata),
    )


def get_project_custom_prompt(project_id: str) -> str | None:
    """Return persisted user-owned project prompt text, if configured."""

    project_data = _read_project_prompt_data(project_id)
    if project_data is None:
        return None
    custom_prompt = project_data.get("settings", {}).get("custom_prompt")
    return custom_prompt or None


def get_default_prompt() -> str:
    """Return the built-in default system prompt text."""

    spec = get_prompt_spec("default")
    if spec is None:
        raise FileNotFoundError("Default prompt spec is missing")
    return spec.system_prompt


def get_project_prompt(project_id: str) -> str:
    """Return project custom prompt text, or the built-in default."""

    return get_project_custom_prompt(project_id) or get_default_prompt()


def update_project_prompt(project_id: str, prompt: Optional[str]) -> bool:
    """Persist user-owned project prompt text in the project JSON settings file."""

    project_file = _project_prompt_file(project_id)
    if not project_file.exists():
        return False

    try:
        with project_file.open("r") as handle:
            project_data = json.load(handle)
        project_data.setdefault("settings", {})
        if prompt:
            project_data["settings"]["custom_prompt"] = prompt
        else:
            project_data["settings"].pop("custom_prompt", None)
        with project_file.open("w") as handle:
            json.dump(project_data, handle, indent=2)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def list_public_prompt_configs() -> list[dict[str, Any]]:
    """Return frontend/API prompt metadata serialized from typed specs."""

    return [spec.public_config() for spec in list_prompt_specs()]


def _project_prompt_file(project_id: str) -> Path:
    return Config.PROJECTS_DIR / f"{project_id}.json"


def _read_project_prompt_data(project_id: str) -> dict[str, Any] | None:
    try:
        with _project_prompt_file(project_id).open("r") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
