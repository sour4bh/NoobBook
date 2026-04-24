"""
Local conftest for tests/config/.

Sets placeholder Supabase env vars before collection so that importing
`app.config` — which transitively loads `context_loader` → Supabase client
initialization — does not raise on a developer machine or CI job without a
populated `.env`. These tests do not touch Supabase; the vars only unblock
module import.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost.test")
# Supabase client validates that the key parses as a JWT; use a harmless
# well-formed placeholder. No network calls are made from these tests.
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0In0."
    "placeholder-signature",
)
