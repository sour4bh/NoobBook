"""
Fixtures for source citation/ingestion/analysis-boundary tests (NBB-702).

The sources domain reaches into Supabase clients at import time:
``app.providers.supabase.__init__`` constructs ``AuthService()``,
which needs ``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY`` to validate.
``app.sources.index._get_client`` fails closed without those env vars too.

These fixtures mirror the bootstrap pattern used by ``tests/api/conftest.py``,
``tests/chat/conftest.py``, and ``tests/test_raw_analysis_gate.py``: set
JWT-shaped dummy env vars before any ``app.*`` import, then replace the
Supabase client singleton with a MagicMock so module-load constructors and
the ``task_service`` startup hook never make real network calls.
"""
import os
from unittest.mock import MagicMock

import pytest

# Supabase env vars must be set before any `app` import triggers
# `AuthService()` / index helpers / `MessageStore()` constructors at module load.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    # JWT-shaped dummy; supabase-py rejects obviously-non-JWT keys on construct.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)
# The Flask test client below routes through the route-handler module, which
# the app-level `before_request` short-circuits with 401 for /api/v1/* when
# `NOOBBOOK_AUTH_REQUIRED=true`. We want to exercise the citation handler's
# 200/404/500 branches, so disable the app-level guard. The `sources_bp`
# project-access check is patched out per-test (see `bypass_project_access`).
os.environ.setdefault("NOOBBOOK_AUTH_REQUIRED", "false")

# Replace the Supabase singleton before any app import. The startup hook in
# `task_service._cleanup_stale_tasks` (see `backend/app/background/tasks.py`)
# otherwise attempts a real network call to Supabase during `create_app`.
from app.providers.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client._client = MagicMock()
_supabase_client._initialized = True

from app import create_app  # noqa: E402


PROJECT_ID = "00000000-0000-0000-0000-000000000aaa"
SOURCE_ID = "11111111-1111-1111-1111-111111111aaa"


@pytest.fixture(scope="session")
def sources_app():
    """Session-scoped Flask app for citation route tests."""
    return create_app("testing")


@pytest.fixture()
def sources_client(sources_app):
    """Flask test client for citation route tests."""
    return sources_app.test_client()


@pytest.fixture()
def bypass_project_access(monkeypatch):
    """Bypass JWT + project-access guards so the citation route runs.

    Two layers run before the route handler:

    1. `api_bp.before_request` (in `app.api.__init__`) validates a JWT and
       returns 401 unconditionally for everything except `/auth/*` and
       `/health` — the env flag does NOT skip this layer. We patch the
       imported `validate_token` symbol so it returns a user_id stand-in.
    2. `sources_bp.before_request` runs `verify_project_access(project_id)`,
       which queries Supabase for project ownership. We patch the
       re-exported symbol to return None so the route's own 200 / 404 /
       500 branches are the test's signal.
    """
    monkeypatch.setattr(
        "app.api.validate_token",
        lambda: "00000000-0000-0000-0000-000000000099",
    )
    monkeypatch.setattr(
        "app.api.sources.verify_project_access",
        lambda project_id: None,
    )
