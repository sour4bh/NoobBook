"""
Canonical project-access check.

`verify_project_access(project_id)` returns None if the current request's
user owns (or has access to) the project, or a Flask `(json-error, 404)`
tuple the route should return directly. 404 (not 403) is intentional: it
leaks less about project existence.

Route files call this through `app.api.auth.middleware` (its
before_request hooks re-export this helper) so the policy stays
authoritative here.
"""

from typing import Optional, Tuple

from flask import Response, g, jsonify


def get_current_user_id() -> Optional[str]:
    """Get the authenticated user's ID from the request context.

    Returns None if no request is active or the caller did not pass the
    `api_bp.before_request` JWT guard.
    """
    return getattr(g, "user_id", None)


def verify_project_access(project_id: str) -> Optional[Tuple[Response, int]]:
    """Verify the current user owns (or may access) the given project.

    Returns None on success. On failure returns a `(json-error, 404)`
    tuple for the route handler to return. Kept 404 (not 403) so the
    response does not distinguish a missing project from an unauthorized
    one.
    """
    # Import lazily: project store is a sibling domain and auth-only
    # callers should not pull it in at module load.
    from app.projects.store import project_service

    user_id = get_current_user_id()
    if not project_service.has_project_access(project_id, user_id=user_id):
        return jsonify({"success": False, "error": "Project not found"}), 404

    return None
