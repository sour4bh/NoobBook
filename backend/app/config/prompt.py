"""
Prompt Config - Manages system prompts for AI interactions.

Educational Note: This module handles loading, storing, and retrieving
prompts used in AI conversations. Projects can have custom prompts or
fall back to the global default.

Prompt Config Structure (consistent across all prompt files):
{
    "version": "2.0",
    "name": "prompt_name",
    "description": "What this prompt is for",
    "model": "claude-sonnet-4-6",
    "max_tokens": 4096,
    "temperature": 0.7,
    "system_prompt": "The actual prompt text...",
    "created_at": "...",
    "updated_at": "..."
}

Prompt Hierarchy:
1. Project custom prompt (if set)
2. Global default prompt (fallback)
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from app.config.runtime import Config
import app.config.asset as asset

logger = logging.getLogger(__name__)


class PromptConfig(dict):
    """
    Dict subclass whose "model" key carries prompt identity and resolves the
    local/bootstrap env fallback dynamically.

    Services in this codebase often cache the result of
    prompt_loader.get_prompt_config(...) in self._prompt_config and reuse it
    for the lifetime of the process. If we mutated config["model"] once at
    load time, an admin changing the model override later would not take
    effect until restart.

    Workspace overrides are resolved later at the Claude call boundary, where
    the project_id is known. The value returned here is still a normal string
    subclass, so existing Anthropic SDK calls continue to accept it.
    """

    def __init__(self, data: Dict[str, Any], prompt_name: Optional[str] = None):
        super().__init__(data)
        # Use object.__setattr__ to bypass dict semantics
        object.__setattr__(self, "_prompt_name", prompt_name)

    def _resolved_model(self) -> Optional[Any]:
        # Lazy import to avoid circular dependency at module load time
        from app.config.model import get_model_override_for_prompt

        prompt_name = object.__getattribute__(self, "_prompt_name")
        if not prompt_name:
            return None
        return get_model_override_for_prompt(prompt_name)

    def __getitem__(self, key):
        if key == "model":
            override = self._resolved_model()
            if override:
                return self._model_value(override)
            return self._model_value(super().__getitem__(key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == "model":
            override = self._resolved_model()
            if override:
                return self._model_value(override)
            value = super().get(key, default)
            return self._model_value(value) if value is not None else value
        return super().get(key, default)

    def _model_value(self, value: Any) -> Any:
        from app.config.model import PromptModel

        if not isinstance(value, str):
            return value
        prompt_name = object.__getattribute__(self, "_prompt_name")
        return PromptModel(value, prompt_name=prompt_name)

    def raw_model(self) -> Optional[str]:
        """
        Return the JSON-baked model, bypassing any admin override.

        Used by the settings UI to show what "Default" actually resolves to
        for each prompt — so admins can see whether selecting Default keeps
        Sonnet, Opus, Haiku, or a mix.
        """
        return super().get("model")


class PromptLoader:
    """
    Loader class for managing system prompts.

    Educational Note: Prompts define how the AI behaves. Different projects
    might need different prompts based on their use case (research, coding,
    learning, etc.).
    """

    def __init__(self):
        """Initialize the prompt service."""
        self.projects_dir = Config.PROJECTS_DIR

    def _resolve_prompt_file(self, prompt_name: str, filename: str) -> Optional[Path]:
        """Find a prompt file by consulting the registry.

        Returns the first existing candidate path, or `None` if none exist.
        `None` preserves the long-standing public contract of callers like
        `get_prompt_config` and `get_agent_prompt` that treat missing prompts
        as a soft miss.
        """
        try:
            return asset.resolve_prompt_path(prompt_name, filename)
        except asset.AssetNotFoundError:
            return None

    def get_default_prompt_config(self) -> Dict[str, Any]:
        """
        Load the full default prompt configuration.

        Educational Note: Returns the complete prompt config including
        model, max_tokens, temperature, and system_prompt. This allows
        services to use consistent settings from a single source.

        Returns:
            Dict with all prompt config fields
        """
        default_prompt_file = self._resolve_prompt_file("default", "default_prompt.json")
        if default_prompt_file is None:
            raise FileNotFoundError(
                "Default prompt is not registered or missing: default_prompt.json"
            )

        with open(default_prompt_file, 'r') as f:
            prompt_data = json.load(f)

            # Handle legacy format where "prompt" was used instead of "system_prompt"
            if "prompt" in prompt_data and "system_prompt" not in prompt_data:
                prompt_data["system_prompt"] = prompt_data.pop("prompt")

            return PromptConfig(prompt_data, prompt_name="default")

    def get_default_prompt(self) -> str:
        """
        Load the global default system prompt text.

        Educational Note: This is used when projects don't have custom prompts.
        It provides a baseline behavior for the AI assistant.

        Returns:
            The default system prompt text
        """
        config = self.get_default_prompt_config()
        return config.get("system_prompt", "")

    def get_project_prompt(self, project_id: str) -> str:
        """
        Get the prompt for a specific project.

        Educational Note: First checks for a custom prompt in project settings,
        then falls back to the global default.

        Args:
            project_id: The project UUID

        Returns:
            The project's system prompt (custom or default)
        """
        project_file = self.projects_dir / f"{project_id}.json"

        try:
            with open(project_file, 'r') as f:
                project_data = json.load(f)
                custom_prompt = project_data.get("settings", {}).get("custom_prompt")

                if custom_prompt:
                    return custom_prompt
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Return default if no custom prompt
        return self.get_default_prompt()

    def get_project_prompt_config(self, project_id: str) -> Dict[str, Any]:
        """
        Get the full prompt config for a specific project.

        Educational Note: Returns the default config but with custom prompt
        if the project has one. This ensures model/max_tokens/temperature
        come from the default config even when using custom prompts.

        Args:
            project_id: The project UUID

        Returns:
            Dict with all prompt config fields
        """
        config = self.get_default_prompt_config()

        # Check for custom prompt override
        project_file = self.projects_dir / f"{project_id}.json"

        try:
            with open(project_file, 'r') as f:
                project_data = json.load(f)
                custom_prompt = project_data.get("settings", {}).get("custom_prompt")

                if custom_prompt:
                    config["system_prompt"] = custom_prompt
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # get_default_prompt_config already returns a PromptConfig tagged with
        # prompt_name="default" so the admin "chat" category override applies.
        return config

    def update_project_prompt(self, project_id: str, prompt: Optional[str]) -> bool:
        """
        Update a project's custom prompt.

        Educational Note: Setting prompt to None removes the custom prompt
        and reverts to the default.

        Args:
            project_id: The project UUID
            prompt: New custom prompt, or None to reset to default

        Returns:
            True if successful, False if project not found
        """
        project_file = self.projects_dir / f"{project_id}.json"

        if not project_file.exists():
            return False

        try:
            with open(project_file, 'r') as f:
                project_data = json.load(f)

            # Ensure settings dict exists
            if "settings" not in project_data:
                project_data["settings"] = {}

            # Update or remove custom prompt
            if prompt:
                project_data["settings"]["custom_prompt"] = prompt
            else:
                # Remove custom prompt to use default
                project_data["settings"].pop("custom_prompt", None)

            # Save updated project
            with open(project_file, 'w') as f:
                json.dump(project_data, f, indent=2)

            return True

        except (json.JSONDecodeError, IOError):
            return False

    def save_default_prompt(self, prompt: str) -> bool:
        """
        Update the global default prompt.

        Educational Note: This affects all projects that don't have
        custom prompts. Use with caution.

        Args:
            prompt: New default prompt text

        Returns:
            True if successful
        """
        try:
            default_prompt_file = asset.resolve_prompt_path(
                "default", "default_prompt.json"
            )
            with open(default_prompt_file, "r") as f:
                prompt_data = json.load(f)
            prompt_data["system_prompt"] = prompt
            prompt_data.pop("prompt", None)
            with open(default_prompt_file, 'w') as f:
                json.dump(prompt_data, f, indent=2)
            return True
        except (asset.AssetNotFoundError, json.JSONDecodeError, IOError):
            return False

    def get_agent_prompt(self, agent_name: str) -> Optional[str]:
        """
        Load a prompt for a specific agent.

        Educational Note: Agents (like web_agent, pdf_agent, etc.) have
        their own specialized prompts stored in registered domain prompt
        directories.

        Args:
            agent_name: Name of the agent (e.g., "web_agent")

        Returns:
            The agent's system prompt, or None if not found
        """
        prompt_file = self._resolve_prompt_file(
            agent_name, f"{agent_name}_prompt.json"
        )
        if prompt_file is None:
            return None

        try:
            with open(prompt_file, 'r') as f:
                prompt_data = json.load(f)
                # Look for system_prompt first (new format), then prompt (legacy)
                return prompt_data.get("system_prompt") or prompt_data.get("prompt")
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def get_prompt_config(self, prompt_name: str) -> Optional[Dict[str, Any]]:
        """
        Load full prompt configuration by name.

        Educational Note: Loads the complete prompt config including
        model, max_tokens, temperature, system_prompt, and user_message.
        Used by domains like chat memory and source summaries for
        specialized AI tasks.

        Args:
            prompt_name: Name of the prompt file (without _prompt.json suffix)
                        e.g., "memory" loads "memory_prompt.json"

        Returns:
            Full prompt config dict, or None if not found
        """
        prompt_file = self._resolve_prompt_file(
            prompt_name, f"{prompt_name}_prompt.json"
        )
        if prompt_file is None:
            return None

        try:
            with open(prompt_file, 'r') as f:
                return PromptConfig(json.load(f), prompt_name=prompt_name)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def list_all_prompts(self) -> list[Dict[str, Any]]:
        """
        List all registered prompt configurations.

        Educational Note: This dynamically reads all registered domain-owned
        *_prompt.json files, making it easy to add new prompts through the
        asset registry without a legacy global prompt directory.

        Returns:
            List of prompt config dicts with all fields
        """
        prompts: list[Dict[str, Any]] = []
        seen_filenames: set[str] = set()

        registered_dirs = [
            directory
            for _prompt_name, directory in asset.iter_registered_prompt_dirs()
        ]
        for directory in registered_dirs:
            if not directory.is_dir():
                continue
            for prompt_file in sorted(directory.glob("*_prompt.json")):
                self._append_prompt_file(prompt_file, prompts, seen_filenames)

        return prompts

    def _append_prompt_file(
        self,
        prompt_file: Path,
        prompts: list[Dict[str, Any]],
        seen_filenames: set,
    ) -> None:
        if prompt_file.name in seen_filenames:
            return
        try:
            with open(prompt_file, "r") as f:
                prompt_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load prompt %s: %s", prompt_file, e)
            return

        # Handle legacy format where "prompt" was used instead of "system_prompt"
        if "prompt" in prompt_data and "system_prompt" not in prompt_data:
            prompt_data["system_prompt"] = prompt_data.pop("prompt")

        prompt_data["filename"] = prompt_file.name
        prompts.append(prompt_data)
        seen_filenames.add(prompt_file.name)


# Singleton instance for easy import
prompt_loader = PromptLoader()
