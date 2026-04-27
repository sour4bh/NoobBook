"""Workspace resolution helpers for settings routes."""

from typing import Tuple

from flask import request

from app.auth.identity import RequestIdentity, get_request_identity
from app.workspaces.settings import workspace_settings_store
from app.workspaces.store import workspace_store


def _requested_workspace_id() -> str | None:
    header_value = (request.headers.get("X-NoobBook-Workspace-Id") or "").strip()
    if header_value:
        return header_value
    query_value = (request.args.get("workspace_id") or "").strip()
    if query_value:
        return query_value
    if request.is_json:
        body = request.get_json(silent=True) or {}
        value = body.get("workspace_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_workspace_context(*, require_manager: bool) -> Tuple[RequestIdentity, str]:
    """Resolve current identity and selected workspace for a settings request."""
    identity = get_request_identity()
    workspace_id = workspace_settings_store.resolve_workspace_id(
        user_id=identity.user_id,
        email=identity.email,
        requested_workspace_id=_requested_workspace_id(),
    )
    if require_manager and not workspace_store.can_manage_workspace(workspace_id, identity.user_id):
        raise PermissionError("Workspace owner or admin role required")
    if not require_manager and not workspace_store.has_workspace_access(workspace_id, identity.user_id):
        raise PermissionError("Workspace access required")
    return identity, workspace_id
