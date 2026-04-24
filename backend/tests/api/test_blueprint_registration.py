"""
Baseline registration checks for every nested blueprint under `api_bp`
(NBB-106).

These tests fail loudly if a blueprint is removed, renamed, or silently
dropped from `backend/app/api/__init__.py`. They also confirm every
blueprint owns at least one URL under the `/api/v1` transport prefix, so
a registration break (missing `register_blueprint` call, import error
in a route module) cannot hide behind a green app factory.
"""

# Blueprints currently registered in backend/app/api/__init__.py. Chat is
# intentionally split into `chats` (CRUD) and `messages` (AI interaction)
# per the ticket — they are distinct route groups that must both resolve.
EXPECTED_BLUEPRINTS = {
    "auth",
    "projects",
    "chats",
    "messages",
    "prompts",
    "google",
    "transcription",
    "settings",
    "sources",
    "studio",
    "brand",
}


def _nested_blueprint_names(app) -> set[str]:
    """Return the set of nested blueprints registered under `api_bp`.

    Endpoints follow the `api.<blueprint>.<func>` naming convention, so we
    can enumerate them directly from the url map without depending on
    Flask internals that vary across versions.
    """
    names: set[str] = set()
    for rule in app.url_map.iter_rules():
        parts = rule.endpoint.split(".")
        if len(parts) >= 3 and parts[0] == "api":
            names.add(parts[1])
    return names


def test_every_expected_blueprint_is_registered(blueprint_app):
    """Every blueprint named in api/__init__.py must be present."""
    registered = _nested_blueprint_names(blueprint_app)
    missing = EXPECTED_BLUEPRINTS - registered
    assert not missing, f"Missing blueprint registrations: {sorted(missing)}"


def test_no_unexpected_blueprints_are_registered(blueprint_app):
    """A new blueprint must be reflected in this test's expected set.

    Fail-loud on additions: adding a blueprint without updating this list
    means domain migrations could silently change the transport surface.
    """
    registered = _nested_blueprint_names(blueprint_app)
    extra = registered - EXPECTED_BLUEPRINTS
    assert not extra, (
        f"Unexpected blueprint(s) registered: {sorted(extra)}. "
        f"If this is intentional, update EXPECTED_BLUEPRINTS in NBB-106 smoke tests."
    )


def test_api_prefix_resolves_to_registered_routes(blueprint_app):
    """Every nested blueprint must expose at least one rule under /api/v1."""
    api_prefix = blueprint_app.config["API_PREFIX"]
    assert api_prefix == "/api/v1", "API_PREFIX changed; update smoke test expectations"

    endpoints_by_bp: dict[str, list[str]] = {}
    for rule in blueprint_app.url_map.iter_rules():
        parts = rule.endpoint.split(".")
        if len(parts) >= 3 and parts[0] == "api":
            bp_name = parts[1]
            if str(rule).startswith(api_prefix):
                endpoints_by_bp.setdefault(bp_name, []).append(str(rule))

    for bp_name in EXPECTED_BLUEPRINTS:
        assert endpoints_by_bp.get(bp_name), (
            f"Blueprint '{bp_name}' registered no routes under {api_prefix}"
        )


def test_health_endpoint_is_public(blueprint_client):
    """Health check is unauthenticated and must always be reachable."""
    resp = blueprint_client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
