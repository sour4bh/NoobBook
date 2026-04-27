"""
Fixtures for backend route smoke tests (NBB-106).

These fixtures are scoped to `backend/tests/api/` to avoid colliding with
shared fixtures owned by NBB-107 and NBB-109. Names are intentionally
narrow (`blueprint_app`, `blueprint_client`) so sibling auth/permissions
tests can add their own fixtures without overlap.

The app factory initializes the Supabase client at import time. These
fixtures set dummy env vars (JWT-shaped so supabase-py's client constructor
accepts them) and replace the Supabase singleton with a MagicMock so
`create_app("testing")` does not make network calls.
"""
import os
from unittest.mock import MagicMock

import pytest

# Supabase env vars must be set before `app` is imported anywhere, because
# `app/providers/supabase/__init__.py` instantiates
# `AuthService()` at module load, which triggers
# `get_supabase()`.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    # JWT-shaped dummy; supabase-py rejects obviously-non-JWT keys on construct.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)
# Replace the Supabase singleton before any app import. The startup hook in
# `task_service._cleanup_stale_tasks` (see `backend/app/background/tasks.py`)
# otherwise attempts a real network call to Supabase during `create_app`.
from app.providers.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client._client = MagicMock()
_supabase_client._initialized = True

from app import create_app  # noqa: E402


@pytest.fixture(scope="session")
def blueprint_app():
    """Flask app instance shared across smoke tests in this package."""
    return create_app("testing")


@pytest.fixture()
def blueprint_client(blueprint_app, monkeypatch):
    """Flask test client for route smoke tests."""
    monkeypatch.setenv("NOOBBOOK_AUTH_REQUIRED", "false")
    return blueprint_app.test_client()
