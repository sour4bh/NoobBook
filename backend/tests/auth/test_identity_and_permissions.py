"""
Unit tests for identity resolution, project access, and permission gating
(NBB-107).

Scope:
- `rbac.get_request_identity` - JWT, dev-headers, and single-user fallbacks.
- `auth_middleware.verify_project_access` - owner vs non-owner responses.
- `permissions.user_has_permission` - positive/negative checks and the
  fail-open branches today's code takes on exceptions and unknown
  categories. NBB-202A is the ticket that tightens those; this suite
  pins current behavior so the tightening cannot ship silently.
- `rbac.require_admin` / `rbac.require_permission` decorator semantics.
"""
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


# ---------------------------------------------------------------------------
# get_request_identity: three-branch resolution
# ---------------------------------------------------------------------------

def _make_flask_app() -> Flask:
    """Minimal Flask app for `test_request_context` without the full API."""
    return Flask(__name__)


def test_identity_from_valid_jwt(auth_required_env):
    """JWT path: Supabase resolves the token, users-table lookup returns
    the role."""
    from app.services.auth import rbac

    app = _make_flask_app()
    with patch.object(rbac, "is_supabase_enabled", return_value=True), patch.object(
        rbac, "get_supabase"
    ) as mock_supabase:
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value = MagicMock(
            user=MagicMock(id="user-jwt", email="jwt@example.com")
        )
        role_resp = MagicMock()
        role_resp.data = [{"role": "admin"}]
        (
            mock_client.table.return_value.select.return_value
            .eq.return_value.execute.return_value
        ) = role_resp
        mock_supabase.return_value = mock_client

        with app.test_request_context(
            "/x", headers={"Authorization": "Bearer jwt-xyz"}
        ):
            identity = rbac.get_request_identity()

    assert identity.user_id == "user-jwt"
    assert identity.email == "jwt@example.com"
    assert identity.role == "admin"
    assert identity.is_authenticated is True
    assert identity.is_admin is True


def test_identity_from_dev_headers(auth_required_env):
    """Dev-headers path: `X-NoobBook-User-Id` wins when Supabase disabled."""
    from app.services.auth import rbac

    app = _make_flask_app()
    with patch.object(rbac, "is_supabase_enabled", return_value=False):
        with app.test_request_context(
            "/x",
            headers={
                "X-NoobBook-User-Id": "dev-user-1",
                "X-NoobBook-Role": "admin",
            },
        ):
            identity = rbac.get_request_identity()

    assert identity.user_id == "dev-user-1"
    assert identity.role == "admin"
    assert identity.is_authenticated is True


def test_identity_single_user_fallback_when_auth_required(auth_required_env):
    """No token, no dev headers, auth required: fallback to DEFAULT_USER_ID
    with the 'user' role (not admin)."""
    from app.services.auth import rbac
    from app.services.data_services.project_service import DEFAULT_USER_ID

    app = _make_flask_app()
    with patch.object(rbac, "is_supabase_enabled", return_value=False):
        with app.test_request_context("/x"):
            identity = rbac.get_request_identity()

    assert identity.user_id == DEFAULT_USER_ID
    assert identity.role == "user"
    assert identity.is_admin is False
    assert identity.is_authenticated is False


def test_identity_single_user_fallback_in_dev_mode(auth_optional_env):
    """Dev/single-user mode: fallback promotes to admin role. Captures
    current documented behavior; NBB-202A will reconsider."""
    from app.services.auth import rbac
    from app.services.data_services.project_service import DEFAULT_USER_ID

    app = _make_flask_app()
    with patch.object(rbac, "is_supabase_enabled", return_value=False):
        with app.test_request_context("/x"):
            identity = rbac.get_request_identity()

    assert identity.user_id == DEFAULT_USER_ID
    assert identity.role == "admin"
    assert identity.is_admin is True
    assert identity.is_authenticated is False


def test_identity_jwt_exception_falls_through_to_fallback(auth_required_env):
    """Captures current fail-open-ish behavior: when the Supabase JWT
    lookup raises, `get_request_identity` silently falls through to
    dev-header / single-user resolution. NBB-202A will tighten; the test
    pins current behavior so any change is explicit."""
    from app.services.auth import rbac

    app = _make_flask_app()
    with patch.object(rbac, "is_supabase_enabled", return_value=True), patch.object(
        rbac, "get_supabase"
    ) as mock_supabase:
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = Exception("network down")
        mock_supabase.return_value = mock_client

        with app.test_request_context(
            "/x", headers={"Authorization": "Bearer bad-jwt"}
        ):
            identity = rbac.get_request_identity()

    # Falls through to single-user fallback rather than raising or 401-ing.
    assert identity.is_authenticated is False


# ---------------------------------------------------------------------------
# verify_project_access: owner vs non-owner
# ---------------------------------------------------------------------------

def test_verify_project_access_owner_returns_none(auth_app):
    """Owner access: `verify_project_access` returns None so the route
    proceeds to its handler.

    `auth_middleware.verify_project_access` does a local
    `from app.services.data_services import project_service` and calls
    `project_service.get_project(...)` on the package-level singleton
    defined in `data_services/__init__.py`. We patch that singleton's
    method directly."""
    from app.utils import auth_middleware
    from app.services import data_services

    with auth_app.test_request_context("/x"), patch.object(
        data_services.project_service,
        "get_project",
        return_value={"id": "proj-1", "user_id": "user-owner"},
    ):
        from flask import g
        g.user_id = "user-owner"
        result = auth_middleware.verify_project_access("proj-1")

    assert result is None


def test_verify_project_access_non_owner_returns_404(auth_app):
    """Non-owner access: returns `(jsonify-error, 404)`. 404 (not 403) is
    intentional — it leaks less about project existence. Captures current
    contract; policy work (NBB-201) preserves or adjusts this knowingly."""
    from app.utils import auth_middleware
    from app.services import data_services

    with auth_app.test_request_context("/x"), patch.object(
        data_services.project_service,
        "get_project",
        return_value=None,
    ):
        from flask import g
        g.user_id = "user-intruder"
        result = auth_middleware.verify_project_access("proj-1")

    assert result is not None
    response, status = result
    assert status == 404
    body = response.get_json()
    assert body == {"success": False, "error": "Project not found"}


# ---------------------------------------------------------------------------
# user_has_permission: positive, negative, and fail-open branches
# ---------------------------------------------------------------------------

def test_user_has_permission_enabled_returns_true():
    """Default all-enabled permissions allow every category/item."""
    from app.services.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": None}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "studio", "presentations") is True


def test_user_has_permission_category_disabled_returns_false():
    """Explicit category disable blocks all items in that category."""
    from app.services.auth import permissions

    stored = {
        "studio": {"enabled": False, "items": {"presentations": True}},
    }
    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": stored}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "studio", "presentations") is False


def test_user_has_permission_item_disabled_returns_false():
    """Item-level disable blocks only that item."""
    from app.services.auth import permissions

    stored = {
        "studio": {"enabled": True, "items": {"presentations": False}},
    }
    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": stored}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "studio", "presentations") is False
        assert permissions.user_has_permission("u1", "studio", "blogs") is True


def test_user_has_permission_fails_open_on_supabase_error():
    """Captures current fail-open behavior: when the Supabase lookup
    raises, `get_user_permissions` returns the all-enabled defaults and
    `user_has_permission` therefore returns True.

    This is the documented fail-open finding from the backlog. NBB-202A
    will tighten this to fail-closed outside dev/single-user mode; this
    test pins current behavior so the change is explicit."""
    from app.services.auth import permissions

    with patch.object(permissions, "_get_supabase", side_effect=Exception("db down")):
        assert permissions.user_has_permission("u1", "data_sources", "database") is True


def test_user_has_permission_unknown_category_fails_open():
    """Captures current fail-open behavior: an unknown category key
    returns True ('unknown category = allowed'). NBB-202A will likely
    flip this; the test pins current behavior."""
    from app.services.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": {}}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "not_a_real_category", "x") is True


# ---------------------------------------------------------------------------
# require_admin / require_permission decorator semantics
# ---------------------------------------------------------------------------

def test_require_admin_rejects_non_admin(auth_required_env):
    """Decorator returns 403 for authenticated non-admin users."""
    from app.services.auth import rbac

    app = _make_flask_app()

    @rbac.require_admin
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="u1", email=None, role="user", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        rbac, "get_request_identity", return_value=identity
    ):
        resp = handler()

    body, status = resp
    assert status == 403
    assert body.get_json()["required_role"] == "admin"


def test_require_admin_rejects_unauthenticated(auth_required_env):
    """Decorator returns 401 when auth required and caller is not
    authenticated."""
    from app.services.auth import rbac

    app = _make_flask_app()

    @rbac.require_admin
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="fallback", email=None, role="user", is_authenticated=False
    )

    with app.test_request_context("/x"), patch.object(
        rbac, "get_request_identity", return_value=identity
    ):
        resp = handler()

    body, status = resp
    assert status == 401


def test_require_admin_allows_admin(auth_required_env):
    """Decorator passes through for admin identity."""
    from app.services.auth import rbac

    app = _make_flask_app()

    @rbac.require_admin
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="admin-1", email=None, role="admin", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        rbac, "get_request_identity", return_value=identity
    ):
        assert handler() == "ok"


def test_require_permission_admin_bypasses_check(auth_required_env):
    """`require_permission` short-circuits for admin identities regardless
    of the user's permission JSONB."""
    from app.services.auth import rbac

    app = _make_flask_app()

    @rbac.require_permission("data_sources", "database")
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="admin-1", email=None, role="admin", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        rbac, "get_request_identity", return_value=identity
    ):
        # Admin bypass means the permissions lookup must never be called.
        with patch(
            "app.services.auth.permissions.user_has_permission"
        ) as mock_check:
            result = handler()

    assert result == "ok"
    assert mock_check.called is False


def test_require_permission_allows_user_with_permission(auth_required_env):
    """Non-admin with the permission granted passes through."""
    from app.services.auth import rbac

    app = _make_flask_app()

    @rbac.require_permission("studio", "presentations")
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="u1", email=None, role="user", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        rbac, "get_request_identity", return_value=identity
    ), patch(
        "app.services.auth.permissions.user_has_permission", return_value=True
    ):
        assert handler() == "ok"


def test_require_permission_blocks_user_without_permission(auth_required_env):
    """Non-admin missing the permission gets a 403 with the standard
    contact-admin message."""
    from app.services.auth import rbac

    app = _make_flask_app()

    @rbac.require_permission("studio", "presentations")
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="u1", email=None, role="user", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        rbac, "get_request_identity", return_value=identity
    ), patch(
        "app.services.auth.permissions.user_has_permission", return_value=False
    ):
        resp = handler()

    body, status = resp
    assert status == 403
    assert body.get_json()["success"] is False
