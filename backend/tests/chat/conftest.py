"""
Fixtures for chat tool contract tests (NBB-701).

The chat loop imports `app.chat.message.store.message_service` at module load,
which constructs a `MessageStore` and refuses to initialize without
SUPABASE_URL / SUPABASE_SERVICE_KEY. The auth/api conftests handle the same
problem; this one mirrors that pattern so chat tests can run independently.
"""
import os
from unittest.mock import MagicMock

# Supabase env vars must be set before any `app` import triggers
# `MessageStore()` / `ChatStore()` constructors at module load.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    # JWT-shaped dummy; supabase-py rejects obviously-non-JWT keys on construct.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)
# Default to dev mode so the policy's "missing user_id allowed" branch is the
# baseline. Tests that need fail-closed semantics flip this with monkeypatch.
os.environ.setdefault("NOOBBOOK_AUTH_REQUIRED", "false")

# Replace the Supabase singleton before any app import so module-load
# constructors and the background-task startup hook do not make network calls.
from app.services.integrations.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client._client = MagicMock()
_supabase_client._initialized = True
