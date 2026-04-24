"""
Per-blueprint route smoke tests (NBB-106).

Each case hits one representative route on a nested blueprint without
authentication and asserts the route is reachable. The assertion is
"not 404": any 2xx/4xx other than 404 proves the route was registered
and routed to its handler (possibly guarded by auth). A 404 would mean
the blueprint failed to register or the route import broke — which is
exactly the regression this suite catches before domain migrations
(Epics 003/004/005) start moving code.

Protected routes assert 401 (the expected unauthenticated guard response
from `api_bp.before_request`). The ticket requires testing guard
behavior rather than bypassing auth.
"""
import pytest

# Dummy project/chat IDs. These routes are guarded by
# `api_bp.before_request`, which returns 401 before the blueprint-level
# project-access check ever runs, so the ID need not exist.
PROJECT_ID = "00000000-0000-0000-0000-000000000000"
CHAT_ID = "00000000-0000-0000-0000-000000000001"


# (blueprint_name, http_method, path, allowed_status_codes)
# allowed_status_codes MUST NOT contain 404 — a 404 here is the failure signal.
REPRESENTATIVE_ROUTES = [
    ("auth", "POST", "/api/v1/auth/signin", {400}),
    ("projects", "GET", "/api/v1/projects", {401}),
    ("chats", "GET", f"/api/v1/projects/{PROJECT_ID}/chats", {401}),
    (
        "messages",
        "POST",
        f"/api/v1/projects/{PROJECT_ID}/chats/{CHAT_ID}/messages",
        {401},
    ),
    ("prompts", "GET", "/api/v1/prompts/default", {401}),
    ("google", "GET", "/api/v1/google/status", {401}),
    ("transcription", "GET", "/api/v1/transcription/status", {401}),
    ("settings", "GET", "/api/v1/settings/api-keys", {401}),
    ("sources", "GET", f"/api/v1/projects/{PROJECT_ID}/sources", {401}),
    ("studio", "GET", "/api/v1/studio/gemini/status", {401}),
    ("brand", "GET", "/api/v1/brand/config", {401}),
]


@pytest.mark.parametrize(
    "blueprint,method,path,allowed",
    REPRESENTATIVE_ROUTES,
    ids=[case[0] for case in REPRESENTATIVE_ROUTES],
)
def test_representative_route_is_registered(
    blueprint_client, blueprint, method, path, allowed
):
    """A 404 means the blueprint or route import broke. Anything else proves
    the route is registered; protected routes land on the expected 401
    guard response, and `/auth/signin` reaches its handler and rejects the
    empty body with 400."""
    if method == "GET":
        response = blueprint_client.get(path)
    elif method == "POST":
        response = blueprint_client.post(path, json={})
    else:
        pytest.fail(f"Unsupported method in smoke table: {method}")

    assert response.status_code != 404, (
        f"Blueprint '{blueprint}' route {method} {path} returned 404 — "
        f"registration or route import likely broke."
    )
    assert response.status_code in allowed, (
        f"Blueprint '{blueprint}' route {method} {path} returned "
        f"{response.status_code}; expected one of {sorted(allowed)}."
    )


def test_unregistered_route_returns_404(blueprint_client):
    """Control case: a path under /api/v1 that matches no blueprint route
    must return 404. If this regresses to 401, it means the app-level auth
    short-circuit re-engaged and future smoke tests would no longer detect
    a dropped registration."""
    resp = blueprint_client.get("/api/v1/definitely-not-a-registered-route")
    assert resp.status_code == 404
