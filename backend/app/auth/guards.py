"""
Route and service guard decorators.

Built on the canonical identity resolver in `app.auth.identity`:
- `require_auth`: deny unauthenticated callers (bypassed in dev mode).
- `require_admin`: deny non-admin callers; distinguishes 401 vs 403.
- `require_permission(category, item)`: per-user module-permission gate.

Admins always pass the permission check; non-admins go through
`app.auth.permissions.user_has_permission`, which is fail-closed in
auth-required mode — unknown categories, unknown items, and DB
failures all return ``False`` here and the decorator turns that into
a 403 response. The same helper falls back to allow in dev /
single-user mode (``NOOBBOOK_AUTH_REQUIRED=false``) so local
development stays frictionless. See `app.auth.permissions` for the
canonical taxonomy and decision rules.
"""

from functools import wraps
from typing import Any

from flask import jsonify

from app.auth.identity import ROLE_ADMIN, T, get_request_identity, is_auth_required


def require_permission(category: str, item: str | None = None):
    """
    Decorator to enforce per-user module permissions.

    Educational Note: Works alongside @require_auth / @require_admin.
    Admins always pass (they have full access). For non-admin users,
    checks the permissions JSONB on the users table.

    Args:
        category: Permission category (e.g., "data_sources", "studio")
        item: Optional sub-item (e.g., "database", "flow_diagrams")

    Usage:
        @require_permission("data_sources", "database")
        def add_database_source(project_id):
            ...
    """
    def decorator(fn: T) -> T:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            identity = get_request_identity()

            # Admins always have full access
            if identity.is_admin:
                return fn(*args, **kwargs)

            # Check permission for non-admin users
            from app.auth.permissions import user_has_permission

            if not user_has_permission(identity.user_id, category, item):
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "This feature is not available for your account. Contact your admin.",
                        }
                    ),
                    403,
                )
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_auth(fn: T) -> T:
    """Decorator to enforce authenticated user (any role)."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_auth_required():
            return fn(*args, **kwargs)

        identity = get_request_identity()
        if not identity.is_authenticated:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Authentication required",
                    }
                ),
                401,
            )
        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def require_admin(fn: T) -> T:
    """Decorator to enforce admin role."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        identity = get_request_identity()
        if is_auth_required() and not identity.is_authenticated:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Authentication required",
                        "required_role": ROLE_ADMIN,
                    }
                ),
                401,
            )
        if not identity.is_admin:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Admin access required",
                        "required_role": ROLE_ADMIN,
                        "role": identity.role,
                    }
                ),
                403,
            )
        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
