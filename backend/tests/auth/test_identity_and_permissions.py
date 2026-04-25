"""
Unit tests for identity resolution, project access, and permission gating
(NBB-107, tightened by NBB-202A).

Scope:
- `rbac.get_request_identity` - JWT, dev-headers, and single-user fallbacks.
- `auth_middleware.verify_project_access` - owner vs non-owner responses.
- `permissions.user_has_permission` - positive/negative checks, unknown
  categories, unknown items, and DB-failure branches. The fail-closed
  behavior landed in NBB-202A; the original NBB-107 fail-open tests have
  been converted in place to cover both auth-required (deny) and dev /
  single-user (allow) modes so the explicit flip is pinned.
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
    from app.auth import identity as identity_mod

    app = _make_flask_app()
    with patch.object(identity_mod, "is_supabase_enabled", return_value=True), patch.object(
        identity_mod, "get_supabase"
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
            identity = identity_mod.get_request_identity()

    assert identity.user_id == "user-jwt"
    assert identity.email == "jwt@example.com"
    assert identity.role == "admin"
    assert identity.is_authenticated is True
    assert identity.is_admin is True


def test_identity_from_dev_headers(auth_required_env):
    """Dev-headers path: `X-NoobBook-User-Id` wins when Supabase disabled."""
    from app.auth import identity as identity_mod

    app = _make_flask_app()
    with patch.object(identity_mod, "is_supabase_enabled", return_value=False):
        with app.test_request_context(
            "/x",
            headers={
                "X-NoobBook-User-Id": "dev-user-1",
                "X-NoobBook-Role": "admin",
            },
        ):
            identity = identity_mod.get_request_identity()

    assert identity.user_id == "dev-user-1"
    assert identity.role == "admin"
    assert identity.is_authenticated is True


def test_identity_single_user_fallback_when_auth_required(auth_required_env):
    """No token, no dev headers, auth required: fallback to DEFAULT_USER_ID
    with the 'user' role (not admin)."""
    from app.auth import identity as identity_mod
    from app.projects.store import DEFAULT_USER_ID

    app = _make_flask_app()
    with patch.object(identity_mod, "is_supabase_enabled", return_value=False):
        with app.test_request_context("/x"):
            identity = identity_mod.get_request_identity()

    assert identity.user_id == DEFAULT_USER_ID
    assert identity.role == "user"
    assert identity.is_admin is False
    assert identity.is_authenticated is False


def test_identity_single_user_fallback_in_dev_mode(auth_optional_env):
    """Dev/single-user mode: fallback promotes to admin role. Captures
    current documented behavior; NBB-202A will reconsider."""
    from app.auth import identity as identity_mod
    from app.projects.store import DEFAULT_USER_ID

    app = _make_flask_app()
    with patch.object(identity_mod, "is_supabase_enabled", return_value=False):
        with app.test_request_context("/x"):
            identity = identity_mod.get_request_identity()

    assert identity.user_id == DEFAULT_USER_ID
    assert identity.role == "admin"
    assert identity.is_admin is True
    assert identity.is_authenticated is False


def test_identity_jwt_exception_falls_through_to_fallback(auth_required_env):
    """Captures current fail-open-ish behavior: when the Supabase JWT
    lookup raises, `get_request_identity` silently falls through to
    dev-header / single-user resolution. NBB-202A will tighten; the test
    pins current behavior so any change is explicit."""
    from app.auth import identity as identity_mod

    app = _make_flask_app()
    with patch.object(identity_mod, "is_supabase_enabled", return_value=True), patch.object(
        identity_mod, "get_supabase"
    ) as mock_supabase:
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = Exception("network down")
        mock_supabase.return_value = mock_client

        with app.test_request_context(
            "/x", headers={"Authorization": "Bearer bad-jwt"}
        ):
            identity = identity_mod.get_request_identity()

    # Falls through to single-user fallback rather than raising or 401-ing.
    assert identity.is_authenticated is False


# ---------------------------------------------------------------------------
# verify_project_access: owner vs non-owner
# ---------------------------------------------------------------------------

def test_verify_project_access_owner_returns_none(auth_app):
    """Owner access: `verify_project_access` returns None so the route
    proceeds to its handler.

    `middleware.verify_project_access` does a local
    `from app.projects.store import project_service` and calls
    `project_service.get_project(...)` on the singleton defined at the
    bottom of `app/projects/store.py`. We patch that singleton's method
    directly."""
    from app.api.auth import middleware
    from app.projects.store import project_service

    with auth_app.test_request_context("/x"), patch.object(
        project_service,
        "get_project",
        return_value={"id": "proj-1", "user_id": "user-owner"},
    ):
        from flask import g
        g.user_id = "user-owner"
        result = middleware.verify_project_access("proj-1")

    assert result is None


def test_verify_project_access_non_owner_returns_404(auth_app):
    """Non-owner access: returns `(jsonify-error, 404)`. 404 (not 403) is
    intentional — it leaks less about project existence. Captures current
    contract; policy work (NBB-201) preserves or adjusts this knowingly."""
    from app.api.auth import middleware
    from app.projects.store import project_service

    with auth_app.test_request_context("/x"), patch.object(
        project_service,
        "get_project",
        return_value=None,
    ):
        from flask import g
        g.user_id = "user-intruder"
        result = middleware.verify_project_access("proj-1")

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
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": None}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "studio", "presentations") is True


def test_user_has_permission_category_disabled_returns_false():
    """Explicit category disable blocks all items in that category."""
    from app.auth import permissions

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
    from app.auth import permissions

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


def test_user_has_permission_fails_closed_on_supabase_error_when_auth_required(
    auth_required_env,
):
    """NBB-202A: when auth is required and the Supabase lookup raises,
    deny instead of returning the all-enabled defaults."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase", side_effect=Exception("db down")):
        assert (
            permissions.user_has_permission("u1", "data_sources", "database")
            is False
        )


def test_user_has_permission_allows_on_supabase_error_in_dev_mode(
    auth_optional_env,
):
    """Dev / single-user mode keeps the historical "default to allow"
    behavior when Supabase is unreachable so local development stays
    frictionless. Pinned explicitly here so the allow path is a
    documented mode-switch rather than a silent fallback."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase", side_effect=Exception("db down")):
        assert (
            permissions.user_has_permission("u1", "data_sources", "database")
            is True
        )


def test_user_has_permission_unknown_category_fails_closed_when_auth_required(
    auth_required_env,
):
    """NBB-202A: unknown category keys are denied in auth-required mode.
    Supabase is not even queried — the taxonomy check short-circuits."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        assert (
            permissions.user_has_permission("u1", "not_a_real_category", "x")
            is False
        )
        # Unknown category must reject before any DB round-trip.
        assert mock_get.called is False


def test_user_has_permission_unknown_category_allows_in_dev_mode(
    auth_optional_env,
):
    """Dev / single-user mode preserves the "unknown = allowed" default
    so local experimentation is unaffected."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        assert (
            permissions.user_has_permission("u1", "not_a_real_category", "x")
            is True
        )
        assert mock_get.called is False


def test_user_has_permission_unknown_item_fails_closed_when_auth_required(
    auth_required_env,
):
    """NBB-202A: an item that is not in ``PERMISSION_TAXONOMY`` is denied
    in auth-required mode even when its category is known."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        assert (
            permissions.user_has_permission("u1", "studio", "made_up_item")
            is False
        )
        # Unknown item also short-circuits before any DB round-trip.
        assert mock_get.called is False


def test_user_has_permission_null_permissions_applies_defaults_for_known_items(
    auth_required_env,
):
    """NBB-202A: when the DB returns a row with ``permissions = NULL``
    (the "use defaults" sentinel), a known item resolves via
    ``DEFAULT_PERMISSIONS`` (all enabled)."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": None}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert (
            permissions.user_has_permission("u1", "studio", "presentations")
            is True
        )


def test_user_has_permission_null_permissions_still_denies_unknown_items(
    auth_required_env,
):
    """NBB-202A: NULL permissions let the known defaults apply, but
    unknown items still deny in auth-required mode — the taxonomy
    check happens before the DB read."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": None}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert (
            permissions.user_has_permission("u1", "studio", "made_up_item")
            is False
        )


def test_user_has_permission_category_only_check_uses_enabled_flag(
    auth_required_env,
):
    """NBB-202A: ``main_chat_service`` calls ``user_has_permission(uid,
    "studio")`` with no item. That category-only shape must keep
    working — return True when the category master toggle is on."""
    from app.auth import permissions

    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": None}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "studio") is True


def test_user_has_permission_category_only_check_respects_master_disable(
    auth_required_env,
):
    """NBB-202A: category-only check must deny when the master
    ``enabled`` flag is False."""
    from app.auth import permissions

    stored = {"studio": {"enabled": False, "items": {}}}
    with patch.object(permissions, "_get_supabase") as mock_get:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"permissions": stored}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        mock_get.return_value = client

        assert permissions.user_has_permission("u1", "studio") is False


def test_user_has_permission_logs_warning_on_db_failure_in_auth_required_mode(
    auth_required_env, caplog,
):
    """NBB-202A: DB failure in auth-required mode must log a warning so
    operators can see the deny-on-error path firing."""
    import logging

    from app.auth import permissions

    caplog.set_level(logging.WARNING, logger=permissions.__name__)

    with patch.object(
        permissions, "_get_supabase", side_effect=Exception("db down")
    ):
        result = permissions.user_has_permission(
            "u1", "data_sources", "database"
        )

    assert result is False
    assert any(
        "Permission lookup failed" in record.getMessage()
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# require_admin / require_permission decorator semantics
# ---------------------------------------------------------------------------

def test_require_admin_rejects_non_admin(auth_required_env):
    """Decorator returns 403 for authenticated non-admin users."""
    from app.auth import identity as rbac
    from app.auth import guards

    app = _make_flask_app()

    @guards.require_admin
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="u1", email=None, role="user", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        guards, "get_request_identity", return_value=identity
    ):
        resp = handler()

    body, status = resp
    assert status == 403
    assert body.get_json()["required_role"] == "admin"


def test_require_admin_rejects_unauthenticated(auth_required_env):
    """Decorator returns 401 when auth required and caller is not
    authenticated."""
    from app.auth import identity as rbac
    from app.auth import guards

    app = _make_flask_app()

    @guards.require_admin
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="fallback", email=None, role="user", is_authenticated=False
    )

    with app.test_request_context("/x"), patch.object(
        guards, "get_request_identity", return_value=identity
    ):
        resp = handler()

    body, status = resp
    assert status == 401


def test_require_admin_allows_admin(auth_required_env):
    """Decorator passes through for admin identity."""
    from app.auth import identity as rbac
    from app.auth import guards

    app = _make_flask_app()

    @guards.require_admin
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="admin-1", email=None, role="admin", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        guards, "get_request_identity", return_value=identity
    ):
        assert handler() == "ok"


def test_require_permission_admin_bypasses_check(auth_required_env):
    """`require_permission` short-circuits for admin identities regardless
    of the user's permission JSONB."""
    from app.auth import identity as rbac
    from app.auth import guards

    app = _make_flask_app()

    @guards.require_permission("data_sources", "database")
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="admin-1", email=None, role="admin", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        guards, "get_request_identity", return_value=identity
    ):
        # Admin bypass means the permissions lookup must never be called.
        with patch(
            "app.auth.permissions.user_has_permission"
        ) as mock_check:
            result = handler()

    assert result == "ok"
    assert mock_check.called is False


def test_require_permission_allows_user_with_permission(auth_required_env):
    """Non-admin with the permission granted passes through."""
    from app.auth import identity as rbac
    from app.auth import guards

    app = _make_flask_app()

    @guards.require_permission("studio", "presentations")
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="u1", email=None, role="user", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        guards, "get_request_identity", return_value=identity
    ), patch(
        "app.auth.permissions.user_has_permission", return_value=True
    ):
        assert handler() == "ok"


def test_require_permission_blocks_user_without_permission(auth_required_env):
    """Non-admin missing the permission gets a 403 with the standard
    contact-admin message."""
    from app.auth import identity as rbac
    from app.auth import guards

    app = _make_flask_app()

    @guards.require_permission("studio", "presentations")
    def handler():
        return "ok"

    identity = rbac.RequestIdentity(
        user_id="u1", email=None, role="user", is_authenticated=True
    )

    with app.test_request_context("/x"), patch.object(
        guards, "get_request_identity", return_value=identity
    ), patch(
        "app.auth.permissions.user_has_permission", return_value=False
    ):
        resp = handler()

    body, status = resp
    assert status == 403
    assert body.get_json()["success"] is False
