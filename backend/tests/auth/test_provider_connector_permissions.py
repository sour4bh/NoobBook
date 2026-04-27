"""
Provider and connector route permission gates (NBB-913).

These tests cover backend-owned gates for features that the frontend already
hides by permission. Direct HTTP calls must hit the same permission source.
"""
from contextlib import ExitStack
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from app.auth.identity import RequestIdentity


PROJECT_ID = "00000000-0000-0000-0000-000000000aaa"
USER_ID = "user-1"
AUTH_HEADERS = {"Authorization": "Bearer valid-jwt"}


def _authenticated_permission_context(
    permission_result: bool | Callable[[str, str, str | None], bool],
) -> ExitStack:
    """Patch API auth plus route permission identity for auth-required tests."""
    stack = ExitStack()

    supabase = MagicMock()
    supabase.auth.get_user.return_value = MagicMock(
        user=MagicMock(id=USER_ID, email="user@example.com")
    )
    stack.enter_context(
        patch("app.api.auth.middleware.get_supabase", return_value=supabase)
    )
    stack.enter_context(
        patch(
            "app.auth.guards.get_request_identity",
            return_value=RequestIdentity(
                user_id=USER_ID,
                email="user@example.com",
                role="user",
                is_authenticated=True,
            ),
        )
    )
    stack.enter_context(
        patch("app.auth.permissions.user_has_permission", side_effect=permission_result)
        if callable(permission_result)
        else patch("app.auth.permissions.user_has_permission", return_value=permission_result)
    )
    return stack


def test_google_status_denies_user_without_drive_permission(auth_client, auth_required_env):
    with _authenticated_permission_context(False), patch(
        "app.api.google.oauth.google_auth_service"
    ) as service:
        response = auth_client.get("/api/v1/google/status", headers=AUTH_HEADERS)

    assert response.status_code == 403
    service.is_configured.assert_not_called()


def test_google_status_allows_user_with_drive_permission(auth_client, auth_required_env):
    identity = RequestIdentity(
        user_id=USER_ID,
        email="user@example.com",
        role="user",
        is_authenticated=True,
    )
    with _authenticated_permission_context(True), patch(
        "app.api.google.oauth.get_request_identity",
        return_value=identity,
    ), patch("app.api.google.oauth.google_auth_service") as service:
        service.is_configured.return_value = True
        service.is_connected.return_value = (False, None)

        response = auth_client.get("/api/v1/google/status", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.get_json()["configured"] is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/google/auth"),
        ("GET", "/api/v1/google/files"),
        ("POST", "/api/v1/google/disconnect"),
    ],
)
def test_google_drive_routes_deny_user_without_drive_permission(
    auth_client,
    auth_required_env,
    method: str,
    path: str,
):
    with _authenticated_permission_context(False):
        response = auth_client.open(path, method=method, headers=AUTH_HEADERS)

    assert response.status_code == 403


def test_transcription_requires_voice_and_elevenlabs_permissions(
    auth_client,
    auth_required_env,
):
    def check(_user_id: str, category: str, item: str | None) -> bool:
        return (category, item) == ("chat_features", "voice_input")

    with _authenticated_permission_context(check), patch(
        "app.api.transcription.routes.transcription_service"
    ) as service:
        response = auth_client.get("/api/v1/transcription/config", headers=AUTH_HEADERS)

    assert response.status_code == 403
    service.get_elevenlabs_config.assert_not_called()


def test_transcription_allows_user_with_voice_and_elevenlabs_permissions(
    auth_client,
    auth_required_env,
):
    with _authenticated_permission_context(True), patch(
        "app.api.transcription.routes.transcription_service"
    ) as service:
        service.is_configured.return_value = True

        response = auth_client.get("/api/v1/transcription/status", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.get_json()["configured"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/settings/mcp",
        "/api/v1/settings/mcp/connection-1/resources",
        "/api/v1/settings/mcp/connection-1/tools",
    ],
)
def test_mcp_read_routes_deny_user_without_mcp_permission(
    auth_client,
    auth_required_env,
    path: str,
):
    with _authenticated_permission_context(False):
        response = auth_client.get(path, headers=AUTH_HEADERS)

    assert response.status_code == 403


def test_mcp_source_creation_denies_user_without_mcp_permission(
    auth_client,
    auth_required_env,
):
    with _authenticated_permission_context(False), patch(
        "app.projects.store.project_service.has_project_access",
        return_value=True,
    ), patch("app.api.sources.uploads.source_service") as source_service:
        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/sources/mcp",
            headers=AUTH_HEADERS,
            json={"connection_id": "conn-1", "resource_uris": ["mcp://resource"]},
        )

    assert response.status_code == 403
    source_service.add_mcp_source.assert_not_called()


def test_dev_mode_fallback_can_reach_gated_transcription_status(
    auth_client,
    auth_optional_env,
):
    with patch("app.api.transcription.routes.transcription_service") as service:
        service.is_configured.return_value = True

        response = auth_client.get("/api/v1/transcription/status")

    assert response.status_code == 200
    assert response.get_json()["configured"] is True
