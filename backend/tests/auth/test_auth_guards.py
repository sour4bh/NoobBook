"""
HTTP-level auth guard tests (NBB-107).

These tests exercise the app-level `api_bp.before_request` JWT guard and
the admin-only route decorator as observed through the Flask test client.
They pin current behavior before NBB-201/NBB-202A/NBB-202B rewrite policy.

Scope:
- Unauthenticated requests to protected routes return 401.
- `/api/v1/auth/*` and `/api/v1/health` bypass the JWT guard.
- Admin-only routes distinguish 401 (unauthenticated) from 403 (wrong role).
- `NOOBBOOK_AUTH_REQUIRED=false` dev/single-user behavior reaches the API
  transport layer and attaches the fallback identity.
"""
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlparse
from unittest.mock import ANY, MagicMock, patch

import pytest

from app.auth.asset_tokens import build_asset_token, parse_asset_token


PROJECT_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Unauthenticated request handling
# ---------------------------------------------------------------------------

def test_protected_route_without_token_returns_401(auth_client):
    """The api-level before_request hook rejects missing auth with 401."""
    response = auth_client.get("/api/v1/projects")
    assert response.status_code == 401
    body = response.get_json()
    assert body == {"success": False, "error": "Authentication required"}


def test_protected_route_with_invalid_bearer_returns_401(auth_client):
    """Invalid tokens fail validation and the guard returns 401."""
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase:
        supabase = MagicMock()
        supabase.auth.get_user.side_effect = Exception("invalid jwt")
        mock_get_supabase.return_value = supabase

        response = auth_client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )

    assert response.status_code == 401


def test_protected_route_with_valid_token_reaches_handler(auth_client):
    """A valid token clears `api_bp.before_request`; request reaches the
    blueprint handler layer (status is anything except 401/404)."""
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase:
        supabase = MagicMock()
        supabase.auth.get_user.return_value = MagicMock(
            user=MagicMock(id="user-abc")
        )
        mock_get_supabase.return_value = supabase

        response = auth_client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer valid-looking-jwt"},
        )

    # Route handler downstream may 200/500 depending on Supabase mocks,
    # but it must not be stopped by the 401 guard.
    assert response.status_code != 401
    assert response.status_code != 404


def test_health_endpoint_skips_auth(auth_client):
    """`/api/v1/health` is explicitly exempt from the guard."""
    response = auth_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_auth_signin_route_skips_jwt_guard(auth_client):
    """`/api/v1/auth/*` routes bypass the JWT guard so login can work."""
    response = auth_client.post("/api/v1/auth/signin", json={})
    # Handler rejects empty body with 400; the JWT guard did not short-circuit.
    assert response.status_code != 401
    assert response.status_code != 404


def test_auth_me_does_not_mint_asset_token_for_unauthenticated_fallback(auth_client):
    """Auth-required /auth/me may describe fallback identity but not asset-auth it."""
    response = auth_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.get_json()
    assert body["user"]["is_authenticated"] is False
    assert body["asset_token"] is None
    assert body["user"]["global_role"] == "user"
    assert body["user"]["is_global_admin"] is False
    assert "workspace" in body


def test_auth_me_returns_workspace_session_context(auth_client):
    """The auth session contract carries selected workspace capabilities."""
    workspace_context = {
        "available_workspaces": [
            {
                "id": "workspace-1",
                "name": "Personal Workspace",
                "role": "owner",
                "owner_user_id": "user-abc",
                "is_personal": True,
            }
        ],
        "selected_workspace": {
            "id": "workspace-1",
            "name": "Personal Workspace",
            "role": "owner",
            "owner_user_id": "user-abc",
            "is_personal": True,
        },
        "selected_workspace_id": "workspace-1",
        "workspace_role": "owner",
        "can_manage_workspace": True,
        "can_create_project": True,
    }
    with patch("app.api.auth.routes.get_request_identity") as identity, patch(
        "app.api.auth.routes.workspace_store"
    ) as store:
        identity.return_value = MagicMock(
            user_id="user-abc",
            email="user@example.com",
            role="user",
            is_admin=False,
            is_authenticated=True,
        )
        store.session_context.return_value = workspace_context

        response = auth_client.get(
            "/api/v1/auth/me",
            headers={"X-NoobBook-Workspace-Id": "workspace-1"},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["workspace"] == workspace_context
    assert body["user"]["global_role"] == "user"
    store.session_context.assert_called_once_with(
        user_id="user-abc",
        email="user@example.com",
        selected_workspace_id="workspace-1",
    )


def test_auth_signin_mints_scoped_asset_token(auth_client):
    """Sign-in returns a separate asset token for browser-loaded media URLs."""
    with patch("app.api.auth.routes.auth_service") as service:
        service.sign_in.return_value = {
            "success": True,
            "user": {"id": "user-abc", "email": "user@example.com"},
            "session": {
                "access_token": "primary-jwt",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "token_type": "bearer",
            },
        }

        response = auth_client.post(
            "/api/v1/auth/signin",
            json={"email": "user@example.com", "password": "password"},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["session"]["access_token"] == "primary-jwt"
    assert body["asset_token"] != "primary-jwt"
    assert parse_asset_token(
        body["asset_token"],
        auth_client.application.config["SECRET_KEY"],
    ) == "user-abc"


def test_auth_signup_returns_personal_workspace_context(auth_client):
    """Signup orchestration creates/returns workspace context outside providers."""
    workspace_context = {
        "available_workspaces": [],
        "selected_workspace": None,
        "selected_workspace_id": None,
        "workspace_role": None,
        "can_manage_workspace": False,
        "can_create_project": False,
    }
    with patch("app.api.auth.routes.auth_service") as service, patch(
        "app.api.auth.routes.workspace_store"
    ) as store:
        service.sign_up.return_value = {
            "success": True,
            "user": {
                "id": "user-abc",
                "email": "user@example.com",
                "global_role": "user",
            },
            "session": {
                "access_token": "primary-jwt",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "token_type": "bearer",
            },
        }
        store.session_context.return_value = workspace_context

        response = auth_client.post(
            "/api/v1/auth/signup",
            json={"email": "user@example.com", "password": "password"},
        )

    assert response.status_code == 200
    body = response.get_json()
    assert body["user"]["global_role"] == "user"
    assert body["workspace"] == workspace_context
    store.session_context.assert_called_once_with(
        user_id="user-abc",
        email="user@example.com",
        selected_workspace_id=None,
    )


def test_dev_mode_api_routes_use_fallback_identity(auth_client, auth_optional_env):
    """NBB-903: API middleware honors dev/single-user mode instead of
    requiring a bearer token after the domain identity resolver falls back."""
    with patch("app.api.projects.routes.project_service") as projects:
        projects.list_all_projects.return_value = []

        response = auth_client.get("/api/v1/projects?workspace_id=workspace-1")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "projects": [], "count": 0}
    projects.list_all_projects.assert_called_once_with(
        user_id="00000000-0000-0000-0000-000000000001",
        workspace_id="workspace-1",
    )


def test_projects_list_requires_workspace_id(auth_client, auth_optional_env):
    """NBB-1004: project listing is scoped to an explicit workspace."""
    response = auth_client.get("/api/v1/projects")

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": "workspace_id is required",
    }


def test_project_content_mutation_requires_editor_role(
    auth_client,
    auth_required_env,
):
    """NBB-1004: private project viewers cannot reach mutating handlers."""
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase, patch(
        "app.projects.store.project_service.has_project_access",
        return_value=True,
    ), patch(
        "app.projects.store.project_service.can_edit_project",
        return_value=False,
    ) as can_edit:
        supabase = MagicMock()
        supabase.auth.get_user.return_value = SimpleNamespace(
            user=SimpleNamespace(id="viewer-user")
        )
        mock_get_supabase.return_value = supabase

        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/chats",
            headers={"Authorization": "Bearer viewer-mutate-jwt"},
            json={"title": "Blocked"},
        )

    assert response.status_code == 403
    assert response.get_json() == {
        "success": False,
        "error": "Project editor role required",
    }
    can_edit.assert_called_once_with(PROJECT_ID, "viewer-user")


def test_project_open_action_allows_viewer_role(auth_client, auth_required_env):
    """NBB-1004: opening a project records access but is not content mutation."""
    opened_project = {
        "id": PROJECT_ID,
        "name": "Project",
        "description": "",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "last_accessed": "2026-01-01T00:00:00",
    }
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase, patch(
        "app.projects.store.project_service.has_project_access",
        return_value=True,
    ), patch(
        "app.projects.store.project_service.can_edit_project"
    ) as can_edit, patch(
        "app.api.projects.routes.project_service.open_project",
        return_value=opened_project,
    ) as open_project:
        supabase = MagicMock()
        supabase.auth.get_user.return_value = SimpleNamespace(
            user=SimpleNamespace(id="viewer-user")
        )
        mock_get_supabase.return_value = supabase

        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/open",
            headers={"Authorization": "Bearer viewer-open-jwt"},
        )

    assert response.status_code == 200
    assert response.get_json()["project"] == opened_project
    open_project.assert_called_once_with(PROJECT_ID, user_id=ANY)
    can_edit.assert_not_called()


# ---------------------------------------------------------------------------
# Browser asset-token policy (NBB-911)
#
# Primary JWTs travel through `Authorization: Bearer` only. Browser-loaded
# media/file/embed routes that cannot attach headers use scoped `asset_token`
# query parameters. JSON/CRUD routes reject all query credentials.
# ---------------------------------------------------------------------------

def test_primary_query_token_rejected_on_json_route(auth_client):
    """JSON listing endpoints reject legacy primary-JWT query tokens."""
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase:
        supabase = MagicMock()
        # Mock still wired in case the middleware mistakenly called it —
        # if the allowlist rejects first (correct behavior), get_user is
        # never hit.
        supabase.auth.get_user.return_value = MagicMock(
            user=MagicMock(id="user-abc")
        )
        mock_get_supabase.return_value = supabase

        response = auth_client.get(
            "/api/v1/projects?token=valid-looking-jwt",
        )

    assert response.status_code == 401
    body = response.get_json()
    assert body == {"success": False, "error": "Authentication required"}
    assert supabase.auth.get_user.called is False


def test_primary_query_token_rejected_on_allowlisted_media_path(auth_client):
    """Asset routes no longer accept the primary JWT in `?token=`."""
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase:
        supabase = MagicMock()
        supabase.auth.get_user.return_value = MagicMock(
            user=MagicMock(id="user-abc")
        )
        mock_get_supabase.return_value = supabase

        response = auth_client.get(
            "/api/v1/projects/proj-1/sources/src-1/download?token=valid-looking-jwt",
        )

    assert response.status_code == 401
    assert supabase.auth.get_user.called is False


def test_asset_token_rejected_on_json_route(auth_client):
    """Scoped asset tokens are not general API credentials."""
    token = build_asset_token(
        "user-abc",
        auth_client.application.config["SECRET_KEY"],
    )

    response = auth_client.get(f"/api/v1/projects?asset_token={quote(token)}")

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "error": "Authentication required"}


def test_asset_token_accepted_on_allowlisted_media_path(auth_client):
    """Browser-loaded media/file/embed routes accept scoped asset tokens."""
    token = build_asset_token(
        "user-abc",
        auth_client.application.config["SECRET_KEY"],
    )

    with patch("app.api.auth.middleware.get_supabase") as mock_get_supabase:
        response = auth_client.get(
            f"/api/v1/projects/proj-1/ai-images/chart.png?asset_token={quote(token)}",
        )

    # Guard passes; the downstream route may 404/500 on mocked storage/catalog
    # access, but it must not be stopped by the 401 guard.
    assert response.status_code != 401
    mock_get_supabase.assert_not_called()


def test_asset_token_rejected_as_bearer(auth_client):
    """Scoped asset tokens cannot be reused as Authorization bearer tokens."""
    token = build_asset_token(
        "user-abc",
        auth_client.application.config["SECRET_KEY"],
    )
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase:
        supabase = MagicMock()
        supabase.auth.get_user.side_effect = Exception("not a supabase jwt")
        mock_get_supabase.return_value = supabase

        response = auth_client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# OAuth callback boundary (NBB-904)
# ---------------------------------------------------------------------------


def test_google_callback_bypasses_bearer_guard_and_rejects_missing_state(
    auth_client, auth_required_env
):
    """OAuth provider redirects cannot attach bearer tokens, so the generic
    guard must not block the callback; missing state still fails closed."""
    response = auth_client.get(
        "/api/v1/google/callback?code=auth-code",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "google_auth=error" in response.headers["Location"]
    assert "message=Google+authentication+failed" in response.headers["Location"]


def test_google_callback_accepts_valid_signed_state(auth_client, auth_required_env):
    """A valid signed OAuth state authorizes the callback before token exchange."""
    from app.api.google import oauth as google_oauth

    with patch.object(google_oauth.google_auth_service, "_store_state_nonce"):
        state = google_oauth.google_auth_service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

    with patch.object(
        google_oauth.google_auth_service,
        "_consume_state_nonce",
        return_value=True,
    ), patch.object(
        google_oauth.google_auth_service,
        "handle_callback",
        return_value=(True, "connected"),
    ) as handle_callback:
        response = auth_client.get(
            f"/api/v1/google/callback?code=auth-code&state={quote(state)}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["Location"] == "http://localhost:5173?google_auth=success"
    handle_callback.assert_called_once_with(
        "auth-code",
        user_id="user-oauth",
        redirect_uri="http://localhost:5001/api/v1/google/callback",
    )


def test_google_callback_rejects_replayed_state_before_token_exchange(
    auth_client, auth_required_env
):
    """A signed state whose nonce is already consumed cannot be replayed."""
    from app.api.google import oauth as google_oauth

    with patch.object(google_oauth.google_auth_service, "_store_state_nonce"):
        state = google_oauth.google_auth_service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

    with patch.object(
        google_oauth.google_auth_service,
        "_consume_state_nonce",
        return_value=False,
    ) as consume, patch.object(
        google_oauth.google_auth_service,
        "handle_callback",
    ) as handle_callback:
        response = auth_client.get(
            f"/api/v1/google/callback?code=auth-code&state={quote(state)}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:5173"
    assert parse_qs(parsed.query) == {
        "google_auth": ["error"],
        "message": ["Google authentication failed"],
    }
    consume.assert_called_once()
    handle_callback.assert_not_called()


def test_google_callback_uses_configured_frontend_origin(
    auth_client,
    auth_required_env,
    monkeypatch,
):
    """Production deployments can redirect back to the configured frontend."""
    from app.api.google import oauth as google_oauth

    monkeypatch.setitem(
        auth_client.application.config,
        "FRONTEND_ORIGIN",
        "https://app.example.test/",
    )
    with patch.object(google_oauth.google_auth_service, "_store_state_nonce"):
        state = google_oauth.google_auth_service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

    with patch.object(
        google_oauth.google_auth_service,
        "_consume_state_nonce",
        return_value=True,
    ), patch.object(
        google_oauth.google_auth_service,
        "handle_callback",
        return_value=(True, "connected"),
    ):
        response = auth_client.get(
            f"/api/v1/google/callback?code=auth-code&state={quote(state)}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["Location"] == "https://app.example.test?google_auth=success"


def test_google_callback_hides_provider_failure_details(
    auth_client,
    auth_required_env,
):
    """Provider exchange errors are logged server-side, not leaked to the URL."""
    from app.api.google import oauth as google_oauth

    with patch.object(google_oauth.google_auth_service, "_store_state_nonce"):
        state = google_oauth.google_auth_service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

    with patch.object(
        google_oauth.google_auth_service,
        "_consume_state_nonce",
        return_value=True,
    ), patch.object(
        google_oauth.google_auth_service,
        "handle_callback",
        return_value=(False, "Failed to authenticate: provider secret detail"),
    ):
        response = auth_client.get(
            f"/api/v1/google/callback?code=auth-code&state={quote(state)}",
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "provider+secret+detail" not in response.headers["Location"]
    assert "message=Google+authentication+failed" in response.headers["Location"]


def test_google_state_nonce_is_consumed_once(auth_client, auth_required_env):
    """The signed state is insufficient without the one-time nonce row."""
    from app.providers.google.auth import GoogleAuthService

    service = GoogleAuthService()
    with patch.object(service, "_store_state_nonce") as store, patch.object(
        service,
        "_consume_state_nonce",
        side_effect=[True, False],
    ) as consume:
        state = service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

        assert service.parse_state(
            state,
            secret_key=auth_client.application.config["SECRET_KEY"],
        ) == "user-oauth"
        assert service.parse_state(
            state,
            secret_key=auth_client.application.config["SECRET_KEY"],
        ) is None

    store.assert_called_once()
    assert consume.call_count == 2


def test_google_state_rejects_wrong_user_nonce(auth_client, auth_required_env):
    """A signed state fails when its nonce row does not match that user."""
    from app.providers.google.auth import GoogleAuthService

    service = GoogleAuthService()
    with patch.object(service, "_store_state_nonce"), patch.object(
        service,
        "_consume_state_nonce",
        return_value=False,
    ) as consume:
        state = service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

        assert service.parse_state(
            state,
            secret_key=auth_client.application.config["SECRET_KEY"],
        ) is None

    consume.assert_called_once()


def test_google_state_rejects_expired_signature(auth_client, auth_required_env):
    """Expired signed state is rejected before nonce consumption."""
    from app.providers.google.auth import GoogleAuthService

    service = GoogleAuthService()
    service.STATE_MAX_AGE_SECONDS = -1
    with patch.object(service, "_store_state_nonce"), patch.object(
        service,
        "_consume_state_nonce",
    ) as consume:
        state = service.build_state(
            user_id="user-oauth",
            secret_key=auth_client.application.config["SECRET_KEY"],
        )

        assert service.parse_state(
            state,
            secret_key=auth_client.application.config["SECRET_KEY"],
        ) is None

    consume.assert_not_called()


def test_google_auth_url_uses_configured_redirect_uri(monkeypatch):
    """Google Console callback URI comes from runtime config, not a dev constant."""
    from app.providers.google.auth import GoogleAuthService

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    service = GoogleAuthService()
    flow = MagicMock()
    flow.authorization_url.return_value = ("https://accounts.google.test/auth", "state")

    with patch(
        "app.providers.google.auth.Flow.from_client_config",
        return_value=flow,
    ) as from_config:
        auth_url = service.get_auth_url(
            user_id="user-oauth",
            state="signed-state",
            redirect_uri="https://api.example.test/api/v1/google/callback",
        )

    assert auth_url == "https://accounts.google.test/auth"
    client_config = from_config.call_args.args[0]
    assert client_config["web"]["redirect_uris"] == [
        "https://api.example.test/api/v1/google/callback",
    ]
    assert from_config.call_args.kwargs["redirect_uri"] == (
        "https://api.example.test/api/v1/google/callback"
    )
    flow.authorization_url.assert_called_once()


def test_google_auth_url_returns_none_when_oauth_credentials_missing(monkeypatch):
    """Missing Google OAuth config fails before building a provider URL."""
    from app.providers.google.auth import GoogleAuthService

    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    assert GoogleAuthService().get_auth_url(
        user_id="user-oauth",
        state="signed-state",
        redirect_uri="https://api.example.test/api/v1/google/callback",
    ) is None


def test_google_refresh_preserves_workspace_binding():
    """Refreshed tokens keep the workspace that owns the OAuth client secret."""
    from app.providers.google.auth import GoogleAuthService

    service = GoogleAuthService()
    credentials = MagicMock()
    credentials.expired = True
    credentials.refresh_token = "refresh-token"
    credentials.valid = True

    saved = {}
    with patch.object(
        service,
        "_load_credentials_with_workspace",
        return_value=(credentials, "workspace-1"),
    ), patch.object(service, "_save_credentials") as save_credentials:
        assert service.get_credentials(user_id="user-1") is credentials

    credentials.refresh.assert_called_once()
    save_credentials.assert_called_once()
    saved["workspace_id"] = save_credentials.call_args.kwargs["workspace_id"]
    assert saved["workspace_id"] == "workspace-1"


# ---------------------------------------------------------------------------
# Admin gate on a real admin-only route (settings/users)
# ---------------------------------------------------------------------------

def _mock_valid_user(supabase_mock, user_id: str, role: str) -> None:
    """Wire a Supabase mock so JWT validation succeeds and the users-table
    role lookup returns `role`."""
    supabase_mock.auth.get_user.return_value = MagicMock(
        user=MagicMock(id=user_id, email=f"{user_id}@example.com")
    )

    # `rbac._load_role_from_users_table` does:
    #   supabase.table("users").select("role").eq("id", user_id).execute()
    role_query = MagicMock()
    role_query.data = [{"role": role}]
    (
        supabase_mock.table.return_value.select.return_value
        .eq.return_value.execute.return_value
    ) = role_query


def test_admin_route_without_auth_returns_401(auth_client):
    """`require_admin` + `is_auth_required()` = 401 for unauthenticated."""
    response = auth_client.get("/api/v1/settings/users")
    assert response.status_code == 401


def test_admin_route_with_non_admin_role_returns_403(auth_client, monkeypatch):
    """Authenticated non-admin users hit 403 with `required_role` in body."""
    monkeypatch.setenv("NOOBBOOK_AUTH_REQUIRED", "true")

    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as auth_supabase, patch(
        "app.auth.identity.get_supabase"
    ) as rbac_supabase, patch(
        "app.auth.identity.is_supabase_enabled", return_value=True
    ):
        auth_mock = MagicMock()
        rbac_mock = MagicMock()
        auth_supabase.return_value = auth_mock
        rbac_supabase.return_value = rbac_mock

        _mock_valid_user(auth_mock, "user-non-admin", "user")
        _mock_valid_user(rbac_mock, "user-non-admin", "user")

        response = auth_client.get(
            "/api/v1/settings/users",
            headers={"Authorization": "Bearer valid-jwt"},
        )

    assert response.status_code == 403
    body = response.get_json()
    assert body["success"] is False
    assert body["required_role"] == "admin"
    assert body["role"] == "user"


def test_admin_route_with_admin_role_passes_admin_gate(auth_client, monkeypatch):
    """Authenticated admin users clear the admin decorator (downstream
    handler may still 500 on mocked DB, but not 401/403)."""
    monkeypatch.setenv("NOOBBOOK_AUTH_REQUIRED", "true")

    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as auth_supabase, patch(
        "app.auth.identity.get_supabase"
    ) as rbac_supabase, patch(
        "app.auth.identity.is_supabase_enabled", return_value=True
    ):
        auth_mock = MagicMock()
        rbac_mock = MagicMock()
        auth_supabase.return_value = auth_mock
        rbac_supabase.return_value = rbac_mock

        _mock_valid_user(auth_mock, "user-admin", "admin")
        _mock_valid_user(rbac_mock, "user-admin", "admin")

        response = auth_client.get(
            "/api/v1/settings/users",
            headers={"Authorization": "Bearer valid-jwt"},
        )

    assert response.status_code != 401
    assert response.status_code != 403


# ---------------------------------------------------------------------------
# Dev / single-user behavior (NOOBBOOK_AUTH_REQUIRED=false)
# ---------------------------------------------------------------------------

def test_rbac_require_auth_bypasses_in_dev_mode(auth_optional_env):
    """Documents current dev/single-user behavior: when
    NOOBBOOK_AUTH_REQUIRED=false, `require_auth` calls the wrapped
    function without running the identity check. NBB-202A will revisit
    this policy — the test captures today's behavior, not the target."""
    from app.auth.guards import require_auth
    from app.auth.identity import is_auth_required

    assert is_auth_required() is False

    @require_auth
    def handler():
        return "ok"

    # No request context, no headers: dev-mode short-circuit returns "ok"
    # because require_auth never reaches the identity path.
    assert handler() == "ok"


def test_rbac_fallback_identity_is_admin_in_dev_mode(
    auth_app, auth_optional_env
):
    """Documents current dev/single-user behavior: with no token and
    NOOBBOOK_AUTH_REQUIRED=false, `get_request_identity` falls through
    to DEFAULT_USER_ID with the admin role. Captures present behavior
    ahead of NBB-202A tightening."""
    from app.auth.identity import get_request_identity
    from app.projects.store import DEFAULT_USER_ID

    with auth_app.test_request_context("/api/v1/anything"):
        identity = get_request_identity()

    assert identity.user_id == DEFAULT_USER_ID
    assert identity.role == "admin"
    assert identity.is_admin is True
    assert identity.is_authenticated is False
