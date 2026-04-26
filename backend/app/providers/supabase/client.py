"""
Supabase client lifecycle.

Lazy module-level singleton: the first `get_client()` call reads the env,
constructs the supabase-py client, and caches it as `_client`. Subsequent
calls reuse the cached client until `reset()` is called.

The client is exposed as module functions because the previous class form
held no per-instance state — `_client` and `_initialized` were always
class-level. NBB-706 collapses the wrapper.

Tests that need to inject a fake client should set the module attributes
directly:

    from app.providers.supabase import supabase_client
    supabase_client._client = MagicMock()
    supabase_client._initialized = True
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

logger = logging.getLogger(__name__)

# Load environment variables once at module import (matches the previous
# class-form behavior; tests still set SUPABASE_URL via conftest before
# import).
load_dotenv()

_client: Optional[Client] = None
_initialized: bool = False


def get_client() -> Client:
    """Return the cached Supabase client, constructing it on first call."""
    global _client, _initialized
    if not _initialized:
        _initialize()
    if _client is None:
        raise RuntimeError("Supabase client failed to initialize")
    return _client


def _initialize() -> None:
    """Build the supabase-py client from `SUPABASE_*` env vars.

    Educational Note: SERVICE_KEY (not anon key) is preferred for
    single-user/local mode because it bypasses Row Level Security (RLS).
    For multi-user production, use the anon key with proper auth.
    """
    global _client, _initialized
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url:
        raise ValueError(
            "SUPABASE_URL environment variable is not set. "
            "Please add it to your .env file."
        )
    if not supabase_key:
        raise ValueError(
            "SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY environment variable is not set. "
            "Please add SUPABASE_SERVICE_KEY to your .env file for single-user mode."
        )

    try:
        _client = create_client(supabase_url, supabase_key)
        _initialized = True
        key_type = "service" if os.getenv("SUPABASE_SERVICE_KEY") else "anon"
        logger.info("Supabase client initialized (%s key): %s", key_type, supabase_url)
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize Supabase client: {exc}")


def is_configured() -> bool:
    """True when both URL and a service/anon key are present in the env."""
    has_url = bool(os.getenv("SUPABASE_URL"))
    has_key = bool(os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    return has_url and has_key


def reset() -> None:
    """Drop the cached client; the next `get_client()` call rebuilds it."""
    global _client, _initialized
    _client = None
    _initialized = False


def get_supabase() -> Client:
    """Public alias kept stable for callers that already imported it."""
    return get_client()


def is_supabase_enabled() -> bool:
    """Public alias kept stable for callers that already imported it."""
    return is_configured()
