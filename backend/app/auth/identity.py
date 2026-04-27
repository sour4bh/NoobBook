"""
Canonical request identity.

One dataclass (`RequestIdentity`) and one resolver (`get_request_identity`)
for every backend caller. The previous `services/auth/rbac.py` mixed these
with the admin/auth/permission decorators; those decorators now live in
`app/auth/guards.py`.

Identity resolution priority:
1. Supabase Auth JWT in `Authorization: Bearer <jwt>`.
2. Dev headers `X-NoobBook-User-Id` / `X-NoobBook-Role`.
3. Single-user fallback to `DEFAULT_USER_ID` — gated on
   `NOOBBOOK_AUTH_REQUIRED=false`, which promotes the fallback identity to
   the admin role. In auth-required mode the fallback stays non-admin and
   is not authenticated; guards reject such callers.
"""

from dataclasses import dataclass
import os
from typing import Any, Callable, Optional, TypeVar

from flask import request

from app.providers.supabase import get_supabase, is_supabase_enabled
from app.projects.store import DEFAULT_USER_ID


ROLE_ADMIN = "admin"
ROLE_USER = "user"
_VALID_ROLES = {ROLE_ADMIN, ROLE_USER}

T = TypeVar("T", bound=Callable[..., Any])


@dataclass(frozen=True)
class RequestIdentity:
    user_id: str
    email: Optional[str]
    role: str
    is_authenticated: bool

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def is_auth_required() -> bool:
    """Check if authentication is required for all API routes.

    Controlled via env var `NOOBBOOK_AUTH_REQUIRED`. Default is true. Set
    to false only for local dev/single-user setups; that flag is the only
    switch that promotes the single-user fallback to the admin role.
    """
    value = os.getenv("NOOBBOOK_AUTH_REQUIRED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _get_bearer_token() -> Optional[str]:
    """Extract the JWT from the request.

    Browser asset tokens are intentionally excluded from identity resolution;
    only the API middleware may accept them on allowlisted asset GET routes.
    """
    auth = request.headers.get("Authorization", "")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


def _load_role_from_users_table(user_id: str) -> Optional[str]:
    if not is_supabase_enabled():
        return None
    try:
        supabase = get_supabase()
        resp = supabase.table("users").select("role").eq("id", user_id).execute()
        if resp.data and isinstance(resp.data, list):
            role = (resp.data[0].get("role") or "").strip().lower()
            return role if role in _VALID_ROLES else None
    except Exception:
        return None
    return None


def get_request_identity() -> RequestIdentity:
    """Resolve the current request's identity and role.

    Returns a `RequestIdentity` even when no credentials are present; the
    caller inspects `is_authenticated` / `is_admin` to decide. Guards in
    `app/auth/guards.py` own the 401/403 responses.
    """
    # 1) Supabase Auth JWT
    token = _get_bearer_token()
    if token and is_supabase_enabled():
        try:
            supabase = get_supabase()
            user_resp = supabase.auth.get_user(token)
            user = getattr(user_resp, "user", None) or user_resp
            user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
            email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
            if user_id:
                role = _load_role_from_users_table(user_id) or ROLE_USER
                return RequestIdentity(
                    user_id=str(user_id),
                    email=str(email) if email else None,
                    role=role,
                    is_authenticated=True,
                )
        except Exception:
            pass  # Fall through to dev/single-user mode

    # 2) Dev headers (useful until full auth UI is wired)
    header_user_id = (request.headers.get("X-NoobBook-User-Id") or "").strip()
    header_role = (request.headers.get("X-NoobBook-Role") or "").strip().lower()
    if header_user_id:
        role = header_role if header_role in _VALID_ROLES else (_load_role_from_users_table(header_user_id) or ROLE_USER)
        return RequestIdentity(
            user_id=header_user_id,
            email=None,
            role=role,
            is_authenticated=True,
        )

    # 3) Single-user fallback. Admin promotion only when NOOBBOOK_AUTH_REQUIRED=false.
    auth_required = is_auth_required()
    fallback_role = ROLE_ADMIN if not auth_required else ROLE_USER
    return RequestIdentity(
        user_id=DEFAULT_USER_ID,
        email=None,
        role=fallback_role,
        is_authenticated=False,
    )
