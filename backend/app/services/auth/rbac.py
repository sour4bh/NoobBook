"""
Legacy re-export shim for `rbac`.

NBB-201 moved the canonical identity resolver to `app.auth.identity`:
- `RequestIdentity`, `get_request_identity`, `is_auth_required`, `ROLE_*`,
  `T`, `_get_bearer_token`, `_load_role_from_users_table`.

This module re-exports those names so existing imports (production and
tests) keep resolving while `NBB-706` removes the shim. Do not add new
code here.
"""

from app.auth.identity import (  # noqa: F401
    RequestIdentity,
    ROLE_ADMIN,
    ROLE_USER,
    T,
    _VALID_ROLES,
    _get_bearer_token,
    _load_role_from_users_table,
    get_request_identity,
    is_auth_required,
)

# Re-export the Supabase helpers the old module exposed at top level. Test
# code (`patch("app.services.auth.rbac.get_supabase")`) relied on these
# being module-level names; keep them available until callers migrate.
from app.services.integrations.supabase import get_supabase, is_supabase_enabled  # noqa: F401
