import os
from unittest.mock import MagicMock


os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)
os.environ.setdefault("NOOBBOOK_AUTH_REQUIRED", "true")

from app.providers.supabase import supabase_client as _supabase_client  # noqa: E402


_supabase_client._client = MagicMock()
_supabase_client._initialized = True
