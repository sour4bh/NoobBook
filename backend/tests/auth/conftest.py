"""
Fixtures for backend auth/permissions tests (NBB-107).

These fixtures are scoped to `backend/tests/auth/` to avoid colliding with
the smoke fixtures owned by NBB-106 and shared fixtures that may land in
the top-level conftest. Names stay narrow (`auth_app`, `auth_client`,
`clear_token_cache`) so sibling test suites can add their own fixtures
without overlap.

The shim below mirrors the NBB-106 conftest verbatim for the
`backend/config.py` vs `backend/app/config/` name collision. The ticket
says to flag-not-fix that collision — the structural fix is tracked as a
backend-charter follow-up (see SPRINT.md Blocker Log, 2026-04-24).

The app factory initializes the Supabase client at import time. These
fixtures set dummy JWT-shaped env vars so supabase-py's constructor
accepts them and replace the Supabase singleton with a MagicMock so
`create_app("testing")` does not make network calls.
"""
import os
from unittest.mock import MagicMock

import pytest

# Supabase env vars must be set before any `app` import triggers
# `AuthService()` / `SupabaseClient.get_client()` at module load.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    # JWT-shaped dummy; supabase-py rejects obviously-non-JWT keys on construct.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)
# Default to auth-required; individual tests flip this to cover the
# dev/single-user case. The `api_bp.before_request` JWT guard still runs
# regardless, so protected routes return 401 for unauthenticated callers.
os.environ.setdefault("NOOBBOOK_AUTH_REQUIRED", "true")

# Replace the Supabase singleton before any app import. The startup hook
# in `task_service._cleanup_stale_tasks` (see `backend/app/background/tasks.py`)
# otherwise attempts a real network call to Supabase during `create_app`.
from app.services.integrations.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client.SupabaseClient._instance = MagicMock()
_supabase_client.SupabaseClient._initialized = True

import app as _app_pkg  # noqa: E402
import config as _top_config  # backend/config.py  # noqa: E402

# `backend/config.py` and `backend/app/config/` share a top-level name.
# Importing the `app.config` submodule (which any of the other tests does
# transitively) rebinds `config` inside the `app` package from the dict in
# `backend/config.py` to the submodule. A later `create_app` call then
# raises `'module' object is not subscriptable`. Restoring the dict before
# importing `create_app` keeps auth tests independent of import order.
# Flag-not-fix per SPRINT.md Blocker Log 2026-04-24.
_app_pkg.config = _top_config.config

from app import create_app  # noqa: E402


@pytest.fixture(scope="session")
def auth_app():
    """Flask app instance shared across auth tests in this package.

    Re-applies the `config` rebinding right before `create_app` because
    other tests may have imported `app.config` between conftest load and
    fixture setup, re-shadowing the dict in the `app` package namespace.
    """
    _app_pkg.config = _top_config.config
    return create_app("testing")


@pytest.fixture()
def auth_client(auth_app):
    """Flask test client for auth route tests."""
    return auth_app.test_client()


@pytest.fixture(autouse=True)
def clear_token_cache():
    """Reset the module-level JWT validation cache between tests.

    `auth_middleware._token_cache` is process-wide. Without this fixture
    a cached positive from one test would leak into the next test's
    monkeypatched `supabase.auth.get_user`.
    """
    from app.utils import auth_middleware

    auth_middleware._token_cache.clear()
    yield
    auth_middleware._token_cache.clear()


@pytest.fixture()
def auth_required_env(monkeypatch):
    """Force NOOBBOOK_AUTH_REQUIRED=true for the test."""
    monkeypatch.setenv("NOOBBOOK_AUTH_REQUIRED", "true")


@pytest.fixture()
def auth_optional_env(monkeypatch):
    """Flip NOOBBOOK_AUTH_REQUIRED=false for dev/single-user cases."""
    monkeypatch.setenv("NOOBBOOK_AUTH_REQUIRED", "false")
