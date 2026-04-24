"""
HTTP-level auth guard tests (NBB-107).

These tests exercise the app-level `api_bp.before_request` JWT guard and
the admin-only route decorator as observed through the Flask test client.
They pin current behavior before NBB-201/NBB-202A/NBB-202B rewrite policy.

Scope:
- Unauthenticated requests to protected routes return 401.
- `/api/v1/auth/*` and `/api/v1/health` bypass the JWT guard.
- Admin-only routes distinguish 401 (unauthenticated) from 403 (wrong role).
- `NOOBBOOK_AUTH_REQUIRED=false` dev/single-user behavior is documented.

Auth is *not* bypassed in dev-mode tests at the HTTP layer: the
`api_bp.before_request` JWT guard still requires a valid token for any
route outside `/auth/*` and `/health`. The dev-mode case instead targets
`rbac.require_auth` / `rbac.require_admin`, which honor `is_auth_required()`.
"""
from unittest.mock import MagicMock, patch

import pytest


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


# ---------------------------------------------------------------------------
# Query-parameter token fallback (used by <img>, <video>, <iframe>)
# ---------------------------------------------------------------------------

def test_query_param_token_fallback_authenticates(auth_client):
    """Browser elements that can't send headers use ?token= — the guard
    accepts valid tokens there too. Captures the current fallback; NBB-201
    will reassess the query-token policy."""
    with patch(
        "app.api.auth.middleware.get_supabase"
    ) as mock_get_supabase:
        supabase = MagicMock()
        supabase.auth.get_user.return_value = MagicMock(
            user=MagicMock(id="user-abc")
        )
        mock_get_supabase.return_value = supabase

        response = auth_client.get(
            "/api/v1/projects?token=valid-looking-jwt",
        )

    assert response.status_code != 401
    assert response.status_code != 404


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
        "app.services.auth.rbac.get_supabase"
    ) as rbac_supabase, patch(
        "app.services.auth.rbac.is_supabase_enabled", return_value=True
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
        "app.services.auth.rbac.get_supabase"
    ) as rbac_supabase, patch(
        "app.services.auth.rbac.is_supabase_enabled", return_value=True
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
    from app.services.auth.rbac import is_auth_required

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
    from app.services.auth.rbac import get_request_identity
    from app.projects.store import DEFAULT_USER_ID

    with auth_app.test_request_context("/api/v1/anything"):
        identity = get_request_identity()

    assert identity.user_id == DEFAULT_USER_ID
    assert identity.role == "admin"
    assert identity.is_admin is True
    assert identity.is_authenticated is False
