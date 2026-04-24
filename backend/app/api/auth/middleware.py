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

Query-token policy (NBB-201): `?token=<jwt>` is honored ONLY for GET
requests whose path matches the browser-asset allowlist (see
`_query_token_allowed`). Every other request — JSON listings, CRUD
POST/PUT/DELETE, chat/message/costs — must send `Authorization: Bearer`.
Browser elements like <img>, <video>, <audio>, <iframe> that cannot set
headers use the allowlisted GET paths (download/preview/assets/etc.).
"""
import functools
import logging
import re
import time
import threading
from typing import Optional, Dict, Tuple

from flask import request, jsonify, g
from app.services.integrations.supabase import get_supabase
from app.auth.access import (  # noqa: F401 — re-export for before_request hooks
    get_current_user_id,
    verify_project_access,
)

logger = logging.getLogger(__name__)


# ─── Query-Token Allowlist ──────────────────────────────────────────────────
# Browser-loaded media/file/embed routes that cannot attach headers. Every
# entry is a GET-only path pattern; JSON/CRUD endpoints must use Bearer.
#
# Patterns match on `request.path` (no query string). Concrete allowlisted
# shapes today:
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
_QUERY_TOKEN_ALLOWED_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/v1/projects/[^/]+/sources/[^/]+/download$"),
    re.compile(r"^/api/v1/projects/[^/]+/brand/assets/[^/]+/download$"),
    re.compile(
        r"^/api/v1/projects/[^/]+/studio/[^/]+/[^/]+/"
        r"(?:preview|download|assets|slides|screenshots)/.+$"
    ),
    re.compile(r"^/api/v1/projects/[^/]+/studio/[^/]+/[^/]+/[^/]+$"),
)


def _query_token_allowed() -> bool:
    """Return True if the current request may read its JWT from `?token=`.

    Only GET requests qualify, and only those whose path matches the
    browser-asset allowlist. POST/PUT/DELETE and JSON listings must use
    `Authorization: Bearer`.
    """
    if request.method != "GET":
        return False
    path = request.path or ""
    return any(pat.match(path) for pat in _QUERY_TOKEN_ALLOWED_PATTERNS)

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


def validate_token() -> Optional[str]:
    """
    Validate the JWT from the Authorization header (or allowlisted `?token=`
    query param) and return the user_id.

    Returns:
        User ID string on success, None on failure

    Educational Note: We call supabase.auth.get_user(jwt) which contacts
    the Supabase Auth server to verify the token signature and expiration.
    The SERVICE_KEY client has permission to validate any user's token.

    Performance: Results are cached for 60 seconds to avoid redundant Auth
    server calls when multiple browser elements (images, videos) load
    simultaneously with the same token.

    Query-token policy (NBB-201): `?token=` is read only when the current
    request matches the browser-asset allowlist (see
    `_query_token_allowed`). JSON listings, CRUD calls, and chat/message
    endpoints must send `Authorization: Bearer` and will 401 otherwise.
    """
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Strip "Bearer "
    elif _query_token_allowed():
        # Narrow fallback: browser media/embed routes only. See the
        # `_QUERY_TOKEN_ALLOWED_PATTERNS` regex list above.
        token = request.args.get('token', '')
    else:
        token = ''

    if not token:
        logger.warning("No auth token found (header=%s, query=%s)", bool(auth_header), bool(request.args.get('token')))
        return None

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
