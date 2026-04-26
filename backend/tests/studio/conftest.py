"""
Fixtures for studio job + background task tests (NBB-703).

`app.background.tasks` instantiates `task_service = TaskService()` at module
load, and `TaskService.__init__` calls `_cleanup_stale_tasks()` which hits
Supabase. Mirrors the auth/api/chat conftest pattern: replace the Supabase
singleton with a MagicMock before any app import touches the background tasks
module.

`app.studio.*` job modules import `app.studio.jobs.store`
which imports `app.services.integrations.supabase` at module load — same hazard,
same fix.
"""
import os
from unittest.mock import MagicMock

# Supabase env vars must be set before any `app` import triggers
# Supabase client instantiation at module load.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    # JWT-shaped dummy; supabase-py rejects obviously-non-JWT keys on construct.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)
os.environ["NOOBBOOK_AUTH_REQUIRED"] = "false"

# Replace the Supabase singleton before any app import so module-load
# constructors and the background-task startup hook do not make network calls.
from app.services.integrations.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client._client = MagicMock()
_supabase_client._initialized = True
