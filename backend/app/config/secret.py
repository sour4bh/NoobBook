"""Runtime secret resolution for providers and connector clients."""

from typing import Any, Optional

from app.workspaces.settings import workspace_settings_store


def get_secret(
    key: str,
    *,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    env_fallback: bool = True,
) -> Optional[str]:
    """Resolve a workspace-scoped secret with optional env fallback."""
    return workspace_settings_store.get_runtime_secret(
        key,
        project_id=project_id,
        workspace_id=workspace_id,
        env_fallback=env_fallback,
    )


def get_project_secret(project_id: Optional[str], key: str) -> Optional[str]:
    """Resolve a secret through the owning workspace of a project."""
    return workspace_settings_store.get_project_provider_secret(project_id, key)


def get_project_settings(project_id: Optional[str]) -> dict[str, Any]:
    """Resolve non-secret settings through the owning workspace of a project."""
    return workspace_settings_store.get_project_settings(project_id)
