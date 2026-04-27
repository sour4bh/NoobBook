"""
Auth Middleware - JWT validation for protected routes.

Educational Note: This middleware validates JWT tokens issued by Supabase Auth.
We keep using the SERVICE_KEY Supabase client for database queries (bypasses RLS),
but validate the user's JWT to extract their user_id. This is simpler than
switching to ANON_KEY and lets the backend act as a trusted server.

Token Validation Cache: We cache successful token validations for 60 seconds
to avoid hitting Supabase Auth on every request. This prevents failures when
many concurrent requests (e.g., loading multiple images) overwhelm the Auth
server. JWTs are already self-validating (signed + expiry), so a short cache
window is safe — even if a token is revoked, the cache expires quickly.

Asset-token policy (NBB-911): primary Supabase JWTs are accepted only from
`Authorization: Bearer`. Browser-loaded assets that cannot attach headers use
short-lived `?asset_token=` values, and only on the allowlisted GET paths below.
"""
import functools
import logging
import re
import threading
import time
from typing import Optional, Dict, Tuple

from flask import current_app, request, jsonify, g
from app.auth.asset_tokens import parse_asset_token
from app.providers.supabase import get_supabase
from app.auth.access import (  # noqa: F401 — re-export for before_request hooks
    get_current_user_id,
    verify_project_access,
)

logger = logging.getLogger(__name__)


# ─── Asset-Token Allowlist ──────────────────────────────────────────────────
# Browser-loaded media/file/embed routes that cannot attach headers. Every
# entry is a GET-only path pattern; JSON/CRUD endpoints must use Bearer JWTs.
#
# Patterns match on `request.path` (no query string). Concrete allowlisted
# shapes today:
#   /api/v1/projects/<id>/ai-images/<filename>
#   /api/v1/projects/<id>/sources/<source_id>/download
#   /api/v1/projects/<id>/brand/assets/<asset_id>/download
#   /api/v1/projects/<id>/studio/<category>/<job_id>/<filename>
#   /api/v1/projects/<id>/studio/<category>/<job_id>/<segment>/<filename...>
#     where <segment> is one of preview, download, assets, slides,
#     screenshots — all binary/HTML file-serving subpaths. `<filename...>`
#     allows nested paths (e.g. websites serve assets under nested dirs).
#
# The patterns stay loose enough to cover new studio categories without
# code changes, but strict enough that no JSON listing (e.g.
# `/studio/<cat>-jobs`, `/studio/<cat>-jobs/<id>`) slips through.
_ASSET_TOKEN_ALLOWED_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/v1/projects/[^/]+/ai-images/[^/]+$"),
    re.compile(r"^/api/v1/projects/[^/]+/sources/[^/]+/download$"),
    re.compile(r"^/api/v1/projects/[^/]+/brand/assets/[^/]+/download$"),
    re.compile(
        r"^/api/v1/projects/[^/]+/studio/[^/]+/[^/]+/"
        r"(?:preview|download|assets|slides|screenshots)/.+$"
    ),
    re.compile(r"^/api/v1/projects/[^/]+/studio/[^/]+/[^/]+/[^/]+$"),
)


def _asset_token_allowed() -> bool:
    """Return True if the current request may read `?asset_token=`.

    Only GET requests qualify, and only those whose path matches the
    browser-asset allowlist. POST/PUT/DELETE and JSON listings must use a
    primary JWT in `Authorization: Bearer`.
    """
    if request.method != "GET":
        return False
    path = request.path or ""
    return any(pat.match(path) for pat in _ASSET_TOKEN_ALLOWED_PATTERNS)

# ─── Token Validation Cache ─────────────────────────────────────────────────
# Educational Note: Without caching, every API request triggers an HTTP call
# to Supabase Auth (get_user). When a page loads multiple images simultaneously,
# 3+ concurrent get_user calls can overwhelm the Auth server, causing 401s.
# Caching the result for 60 seconds fixes this while staying security-safe.
_token_cache: Dict[str, Tuple[str, float]] = {}  # {token: (user_id, expires_at)}
_TOKEN_CACHE_TTL = 60  # seconds
_cache_lock = threading.Lock()


def _get_cached_user_id(token: str) -> Optional[str]:
    """Check if a token has a valid cached validation result."""
    cached = _token_cache.get(token)
    if cached:
        user_id, expires_at = cached
        if time.time() < expires_at:
            return user_id
        # Expired — remove from cache
        with _cache_lock:
            _token_cache.pop(token, None)
    return None


def _cache_token(token: str, user_id: str) -> None:
    """Cache a successful token validation result."""
    with _cache_lock:
        _token_cache[token] = (user_id, time.time() + _TOKEN_CACHE_TTL)
        # Prevent unbounded growth — evict expired entries when cache gets large
        if len(_token_cache) > 100:
            now = time.time()
            expired = [k for k, (_, exp) in _token_cache.items() if now >= exp]
            for k in expired:
                del _token_cache[k]


def _validate_bearer_token(token: str) -> Optional[str]:
    """
    Validate the Supabase JWT from the Authorization header and return user_id.

    Educational Note: We call supabase.auth.get_user(jwt) which contacts
    the Supabase Auth server to verify the token signature and expiration.
    The SERVICE_KEY client has permission to validate any user's token.

    Results are cached for 60 seconds to avoid redundant Auth server calls.
    """
    # Check cache first — avoids redundant Supabase Auth calls
    cached_user_id = _get_cached_user_id(token)
    if cached_user_id:
        return cached_user_id

    try:
        supabase = get_supabase()
        user_response = supabase.auth.get_user(token)

        if not user_response or not user_response.user:
            logger.warning("Auth get_user returned no user")
            return None

        user_id = str(user_response.user.id)
        _cache_token(token, user_id)
        return user_id
    except Exception as e:
        logger.warning("Token validation failed: %s: %s", type(e).__name__, e)
        return None


def validate_token() -> Optional[str]:
    """
    Validate request credentials and return the user_id.

    Primary JWTs are accepted from `Authorization: Bearer` only. Allowlisted
    browser asset GETs may instead pass a scoped `?asset_token=` value.
    """
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        return _validate_bearer_token(auth_header[7:])

    if _asset_token_allowed():
        user_id = parse_asset_token(
            token=request.args.get('asset_token', ''),
            secret_key=str(current_app.config["SECRET_KEY"]),
        )
        if user_id:
            return user_id

    logger.warning(
        "No valid auth token found (header=%s, asset_query=%s, legacy_query=%s)",
        bool(auth_header),
        bool(request.args.get('asset_token')),
        bool(request.args.get('token')),
    )
    return None


def require_auth(f):
    """
    Decorator that requires a valid Supabase JWT in the Authorization header.

    Sets g.user_id on success. Returns 401 on failure.
    Use this for routes that need explicit auth (e.g., /auth/me, /auth/logout).
    Most routes are protected by the before_request hook in api/__init__.py instead.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user_id = validate_token()

        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        g.user_id = user_id
        return f(*args, **kwargs)

    return decorated
