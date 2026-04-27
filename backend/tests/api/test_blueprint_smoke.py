"""
Per-blueprint route smoke tests (NBB-106).

Each case hits one representative route on a nested blueprint without
authentication and asserts the route is reachable. The assertion is
"not 404": any 2xx/4xx other than 404 proves the route was registered
and routed to its handler (possibly guarded by auth). A 404 would mean
the blueprint failed to register or the route import broke — which is
exactly the regression this suite catches before domain migrations
(Epics 003/004/005) start moving code.

Protected route guard behavior is owned by tests/auth/. This suite runs with
`NOOBBOOK_AUTH_REQUIRED=false` so missing-route 404s are not masked by the
app-level guard, then asserts every representative route is registered.
"""
import pytest

# Dummy project/chat IDs. Dev-mode route smoke tests can reach handlers, but
# every route should still return something other than 404.
PROJECT_ID = "00000000-0000-0000-0000-000000000000"
CHAT_ID = "00000000-0000-0000-0000-000000000001"


# (blueprint_name, http_method, path)
REPRESENTATIVE_ROUTES = [
    ("auth", "POST", "/api/v1/auth/signin"),
    ("projects", "GET", "/api/v1/projects"),
    ("chats", "GET", f"/api/v1/projects/{PROJECT_ID}/chats"),
    (
        "messages",
        "POST",
        f"/api/v1/projects/{PROJECT_ID}/chats/{CHAT_ID}/messages",
    ),
    ("prompts", "GET", "/api/v1/prompts/default"),
    ("google", "GET", "/api/v1/google/status"),
    ("transcription", "GET", "/api/v1/transcription/status"),
    ("settings", "GET", "/api/v1/settings/api-keys"),
    ("sources", "GET", f"/api/v1/projects/{PROJECT_ID}/sources"),
    ("studio", "GET", "/api/v1/studio/gemini/status"),
    ("brand", "GET", "/api/v1/brand/config"),
]


@pytest.mark.parametrize(
    "blueprint,method,path",
    REPRESENTATIVE_ROUTES,
    ids=[case[0] for case in REPRESENTATIVE_ROUTES],
)
def test_representative_route_is_registered(blueprint_client, blueprint, method, path):
    """A 404 means the blueprint or route import broke. Anything else proves
    the route is registered."""
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


def test_unregistered_route_returns_404(blueprint_client):
    """Control case: a path under /api/v1 that matches no blueprint route
    must return 404. If this regresses to 401, it means the app-level auth
    short-circuit re-engaged and future smoke tests would no longer detect
    a dropped registration."""
    resp = blueprint_client.get("/api/v1/definitely-not-a-registered-route")
    assert resp.status_code == 404
