"""OpenAI Responses client boundary."""

from __future__ import annotations

from typing import Optional

from openai import OpenAI

from app.config.secret import get_secret


_client: Optional[OpenAI] = None


def get_client(
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> OpenAI:
    """Return an OpenAI client, preferring workspace/project scoped secrets."""
    workspace_api_key = get_secret(
        "OPENAI_API_KEY",
        project_id=project_id,
        workspace_id=workspace_id,
        env_fallback=False,
    )
    if workspace_api_key:
        return OpenAI(api_key=workspace_api_key)

    global _client
    if _client is None:
        api_key = get_secret("OPENAI_API_KEY", env_fallback=True)
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        _client = OpenAI(api_key=api_key)
    return _client


def reload_config() -> None:
    """Reset the cached global OpenAI client after settings changes."""
    global _client
    _client = None
