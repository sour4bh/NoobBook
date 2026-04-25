"""
Tests for ``ToolCapabilityPolicy`` (NBB-202B).

The policy classifies every Claude-visible tool from the NBB-207C
inventory and enforces three guarantees:

1. Unclassified tools are never exposable, so analysis tools cannot
   slip in without a capability entry.
2. Capability-aware exposure honors the NBB-202A fail-closed contract
   for missing ``user_id`` and DB failures, and routes through
   ``permissions.user_has_permission`` so the existing permission
   tests cover the same paths.
3. Required-permission entries match the NBB-202A taxonomy.

These tests live in ``backend/tests/auth/`` next to the permissions
suite so the auth fixture set (Supabase singleton mocked,
``NOOBBOOK_AUTH_REQUIRED`` env var toggled) is available.
"""
from unittest.mock import MagicMock, patch

import pytest


# Importing the module triggers central registration. Keep the import
# at module scope so the registry is populated before the parametrized
# inventory test collects.
from app.auth import permissions, tool_capabilities
from app.auth.tool_policy import (
    CapabilityLevel,
    RequiredPermission,
    ToolCapability,
    ToolScope,
    tool_capability_policy,
)


# Importing the analysis module ensures its entries are registered
# before tests inspect the registry. ``ensure_capabilities_loaded``
# also covers this, but explicit import here keeps the intent visible.
from app.sources.analysis import tool_capabilities as analysis_capabilities  # noqa: F401
from app.auth.permissions import PERMISSION_TAXONOMY, KNOWN_CATEGORIES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_supabase_response(perms_value):
    """Wrap a permissions JSONB value in a Supabase-shaped response."""
    client = MagicMock()
    resp = MagicMock()
    resp.data = [{"permissions": perms_value}]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
    return client


# ---------------------------------------------------------------------------
# Policy primitives
# ---------------------------------------------------------------------------


def test_unclassified_tool_is_never_exposable(auth_required_env):
    """AC#3: a tool with no capability entry must not be exposable.

    Without this rule, a missed classification would silently default
    to whatever permission heuristic the call site happened to use.
    """
    assert tool_capability_policy.is_exposable_for(
        "user-1", "definitely_not_a_registered_tool"
    ) is False


def test_unclassified_tool_denied_in_dev_mode_too(auth_optional_env):
    """Even dev mode must refuse unclassified tools — AC#3 is a hard
    invariant, not a fail-closed-only rule. Otherwise a developer
    could ship an unclassified analysis tool and it would land in
    production after auth is enabled."""
    assert tool_capability_policy.is_exposable_for(
        "user-1", "definitely_not_a_registered_tool"
    ) is False


def test_missing_user_id_denied_in_auth_required(auth_required_env):
    """Closes the legacy ``not user_id or ...`` short-circuit.

    Even for a registered tool, ``user_id=None`` denies in
    auth-required mode. Mirrors ``user_has_permission`` fail-closed
    semantics from NBB-202A.
    """
    assert tool_capability_policy.is_exposable_for(None, "search_sources") is False


def test_missing_user_id_allowed_in_dev_mode(auth_optional_env):
    """Dev / single-user mode keeps the historical default-allow for
    missing identity so local development without auth stays
    frictionless."""
    assert tool_capability_policy.is_exposable_for(None, "search_sources") is True


def test_classified_tool_with_user_calls_user_has_permission(auth_required_env):
    """Verifies the policy hands off to ``permissions.user_has_permission``
    using the entry's required (category, item). The policy lazy-imports
    the symbol inside ``is_exposable_for``, so patching the source
    module's attribute is the right interception point.
    """
    with patch.object(
        permissions, "user_has_permission", return_value=True
    ) as mock_perm:
        allowed = tool_capability_policy.is_exposable_for(
            "user-1", "store_memory"
        )
    assert allowed is True
    mock_perm.assert_called_once_with("user-1", "chat_features", "memory")


def test_classified_tool_denied_when_permission_denied(auth_required_env):
    """When ``user_has_permission`` returns False, exposure is denied
    even for a classified tool."""
    with patch.object(
        permissions, "user_has_permission", return_value=False
    ):
        assert tool_capability_policy.is_exposable_for(
            "user-1", "studio_signal"
        ) is False


def test_register_during_held_lock_does_not_deadlock():
    """Regression: ``ensure_capabilities_loaded`` acquires the registry
    lock and then triggers side-effect imports whose top-level code
    calls ``register`` on the same lock from the same thread. A
    non-reentrant ``Lock`` deadlocks that path; ``RLock`` keeps it
    safe. Simulating the same pattern with ``register`` called from
    inside a ``with policy._lock:`` block reproduces the lock contention
    deterministically without relying on Python's module-cache state.
    """
    import threading
    from app.auth.tool_policy import ToolCapabilityPolicy

    fresh_policy = ToolCapabilityPolicy()

    completed = threading.Event()

    def _run() -> None:
        with fresh_policy._lock:
            fresh_policy.register(
                ToolCapability(
                    name="reentrant_probe",
                    owner="auth/",
                    required_permission=RequiredPermission(
                        category="chat_features"
                    ),
                    scope=ToolScope.GLOBAL,
                    level=CapabilityLevel.READ_ONLY,
                    external_side_effects=False,
                    requires_user_confirmation=False,
                    audit_log=False,
                )
            )
        completed.set()

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=2)
    assert completed.is_set(), (
        "register() deadlocked while the same thread held the registry lock"
    )


def test_register_rejects_conflicting_redefinition():
    """Two different classifications for the same tool name must not
    quietly coexist; that would silently change a deny/allow decision."""
    different = ToolCapability(
        name="search_sources",
        owner="other/owner/",
        required_permission=RequiredPermission(
            category="data_sources", item="csv"
        ),
        scope=ToolScope.GLOBAL,
        level=CapabilityLevel.DESTRUCTIVE,
        external_side_effects=True,
        requires_user_confirmation=True,
        audit_log=True,
    )
    with pytest.raises(ValueError):
        tool_capability_policy.register(different)


# ---------------------------------------------------------------------------
# Coverage: every Claude-visible tool from NBB-207C has an entry
# ---------------------------------------------------------------------------


# The inventory is derived from disk so a future regression of the
# "registry key drifted from JSON ``name`` field" class of bug is
# caught automatically: walk every tool JSON, read its ``name`` field
# (the value Claude actually sees in ``tool_choice``), and assert each
# one has a registered capability.
#
# ``backend/app/services/tools/chat_tools/compact_tool.json`` is a
# placeholder with 0 bytes, so ``json.load`` raises and we skip it
# explicitly. The chat-orchestrator ``compact`` entry classifies the
# placeholder defensively so the registry still answers a decision
# when the JSON is fleshed out.
#
# Two JSON ``name`` values are reused across files (``query_runner``
# in database_agent + freshdesk_agent, and ``web_search`` in link +
# deep-research). The registry holds one canonical entry per category
# and uses prefixed keys for the freshdesk + research variants to
# avoid collision; the alias map below resolves those JSON names back
# to their registered key.
#
# ``schema_info`` is freshdesk-only (the database agent uses
# ``schema_fetcher``), but the registry uses the prefixed key
# ``freshdesk_schema_info`` for symmetry with ``freshdesk_query_runner``;
# include it in the alias map so the JSON ``name`` test passes for it.
_TOOL_JSON_GLOBS = (
    "app/**/tools/*.json",
    "app/services/tools/**/*.json",
)


# Maps a JSON ``name`` to the registry key that classifies it. Used
# for the small set of names where the registry key intentionally
# diverges from the JSON ``name`` — collision disambiguation today,
# tracked under NBB-303 for the (category, name) key strategy.
_NAME_REGISTRY_ALIASES = {
    # link + deep-research both expose ``web_search``; the link
    # variant takes the canonical key, and the research variant is
    # registered as ``research_web_search``.
    ("web_search", "app/sources/analysis/research/tools/web_search.json"):
        "research_web_search",
    # database + freshdesk both expose ``query_runner``; database
    # takes the canonical key, freshdesk gets prefixed.
    ("query_runner", "app/services/tools/freshdesk_agent/query_runner.json"):
        "freshdesk_query_runner",
    # ``schema_info`` is freshdesk-only but registered with a prefix
    # for symmetry with ``freshdesk_query_runner``.
    ("schema_info", "app/services/tools/freshdesk_agent/schema_info.json"):
        "freshdesk_schema_info",
}


def _discover_tool_json_inventory():
    """Walk every tool JSON and return ``(json_name, file_path)`` tuples.

    Sorted output keeps pytest parametrize IDs stable across runs.
    """
    import glob
    import json
    import os

    backend_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    seen_paths = set()
    inventory = []
    for pattern in _TOOL_JSON_GLOBS:
        for path in glob.glob(
            os.path.join(backend_dir, pattern), recursive=True
        ):
            rel = os.path.relpath(path, backend_dir)
            if rel in seen_paths:
                continue
            seen_paths.add(rel)
            try:
                with open(path) as fh:
                    data = json.load(fh)
            except json.JSONDecodeError:
                # Empty placeholder JSON (compact_tool.json today);
                # the central registry classifies the placeholder so
                # the inventory still has it, but we cannot read its
                # ``name`` from disk.
                continue
            name = data.get("name")
            if not name:
                continue
            inventory.append((name, rel))
    return tuple(sorted(inventory))


_TOOL_JSON_INVENTORY = _discover_tool_json_inventory()


@pytest.mark.parametrize("json_name,json_path", _TOOL_JSON_INVENTORY)
def test_every_tool_json_name_has_registered_capability(json_name, json_path):
    """AC#1: every Claude-visible tool's JSON ``name`` field maps to a
    registered ``ToolCapability``.

    Derived from disk so a future regression of "registry key drifted
    from JSON name" (the exact class of bug the recovery pass fixes)
    fails this test instead of slipping through. For the small set of
    JSON names that share a key across files, ``_NAME_REGISTRY_ALIASES``
    redirects to the prefixed registry key.
    """
    tool_capability_policy.ensure_capabilities_loaded()
    expected_key = _NAME_REGISTRY_ALIASES.get((json_name, json_path), json_name)
    assert tool_capability_policy.has(expected_key), (
        f"Tool JSON {json_path!r} declares name={json_name!r} but the "
        f"capability policy has no entry for {expected_key!r}. Registry "
        f"key must match the JSON ``name`` field (or the alias map) so "
        f"``tool_choice={{type: tool, name: <name>}}`` lands on a real "
        f"capability."
    )


def test_compact_placeholder_has_capability_entry():
    """``compact_tool.json`` is a 0-byte placeholder so the disk-derived
    test cannot read its ``name``. The chat-orchestrator entry still
    classifies it so a future fleshed-out JSON has a policy decision
    waiting for it."""
    tool_capability_policy.ensure_capabilities_loaded()
    assert tool_capability_policy.has("compact") is True


def test_save_memory_capability_entry_exists():
    """``save_memory`` is the JSON ``name`` for ``manage_memory_tool.json``;
    ``memory_service`` calls it via forced ``tool_choice``. Pin the
    classification so a regression is caught alongside the disk-derived
    AC#1 test (which already covers it, but a named test makes the
    intent explicit)."""
    cap = tool_capability_policy.get("save_memory")
    assert cap is not None
    assert cap.required_permission == RequiredPermission(
        category="chat_features", item="memory"
    )
    assert cap.level == CapabilityLevel.WRITE_CAPABLE


def test_mcp_generic_sentinel_is_registered():
    """MCP tools are dynamic; the policy still must answer
    ``is_exposable_for`` for them. The sentinel ``mcp`` entry plus
    ``mcp_capability_for`` cover the dynamic case."""
    assert tool_capability_policy.has("mcp") is True


def test_mcp_capability_for_generates_per_name_entry():
    cap = tool_capabilities.mcp_capability_for("mcp_some_dynamic_tool")
    assert cap.name == "mcp_some_dynamic_tool"
    assert cap.required_permission == RequiredPermission(
        category="integrations", item="mcp"
    )
    assert cap.owner == tool_capabilities.MCP_GENERIC.owner


# ---------------------------------------------------------------------------
# Required permissions match the NBB-202A taxonomy
# ---------------------------------------------------------------------------


def _all_registered_tool_names():
    """Snapshot of every registered tool name for parametrized tests.

    Iterating the registry rather than a worker-curated subset keeps
    these checks aligned with what the policy actually answers; a
    taxonomy drift on any registered tool fails here, not just on the
    names a previous worker happened to remember.
    """
    tool_capability_policy.ensure_capabilities_loaded()
    return tuple(sorted(tool_capability_policy.all_names()))


@pytest.mark.parametrize("tool_name", _all_registered_tool_names())
def test_required_permission_categories_are_known(tool_name):
    """Every entry's ``required_permission.category`` must appear in
    ``PERMISSION_TAXONOMY`` so ``user_has_permission`` does not
    short-circuit to ``_fallback_allow`` on an unknown-category miss.
    """
    cap = tool_capability_policy.get(tool_name)
    assert cap is not None
    assert cap.required_permission.category in KNOWN_CATEGORIES, (
        f"{tool_name!r} declares unknown permission category "
        f"{cap.required_permission.category!r}"
    )


@pytest.mark.parametrize("tool_name", _all_registered_tool_names())
def test_required_permission_items_match_taxonomy(tool_name):
    """If a tool declares a permission item, that item must exist in
    its category. ``None`` (category-only check) is also allowed."""
    cap = tool_capability_policy.get(tool_name)
    assert cap is not None

    item = cap.required_permission.item
    if item is None:
        return  # Category-only check is fine.

    category = cap.required_permission.category
    items = PERMISSION_TAXONOMY.get(category, frozenset())
    assert item in items, (
        f"{tool_name!r} declares item {item!r} not in taxonomy for "
        f"category {category!r}"
    )


# ---------------------------------------------------------------------------
# Named coverage spots from the ticket Verification clause
# ---------------------------------------------------------------------------


def test_source_search_classified_as_read_only_project_scoped():
    cap = tool_capability_policy.get("search_sources")
    assert cap is not None
    assert cap.scope == ToolScope.PROJECT
    assert cap.level == CapabilityLevel.READ_ONLY
    assert cap.external_side_effects is False


def test_memory_classified_as_write_capable_with_audit():
    cap = tool_capability_policy.get("store_memory")
    assert cap is not None
    assert cap.level == CapabilityLevel.WRITE_CAPABLE
    assert cap.audit_log is True
    assert cap.required_permission == RequiredPermission(
        category="chat_features", item="memory"
    )


def test_jira_connector_tool_classified_correctly():
    cap = tool_capability_policy.get("jira_search_issues")
    assert cap is not None
    assert cap.owner.startswith("connectors/jira/")
    assert cap.external_side_effects is True
    assert cap.required_permission == RequiredPermission(
        category="data_sources", item="jira"
    )


def test_studio_signal_classified_correctly():
    cap = tool_capability_policy.get("studio_signal")
    assert cap is not None
    assert cap.owner.startswith("studio/")
    assert cap.required_permission.category == "studio"
    assert cap.required_permission.item is None


def test_csv_analysis_tool_classified_correctly():
    cap = tool_capability_policy.get("analyze_csv_agent")
    assert cap is not None
    assert cap.owner.startswith("sources/analysis/csv/")
    assert cap.required_permission == RequiredPermission(
        category="data_sources", item="csv"
    )


def test_run_analysis_classified_as_destructive():
    """The raw-code analysis tool is destructive; NBB-203 also gates
    execution at the runtime layer, but the policy must already refuse
    exposure unless the data_sources.csv permission is held."""
    cap = tool_capability_policy.get("run_analysis")
    assert cap is not None
    assert cap.level == CapabilityLevel.DESTRUCTIVE
    assert cap.requires_user_confirmation is True


# ---------------------------------------------------------------------------
# End-to-end through ``permissions.user_has_permission``
# ---------------------------------------------------------------------------


def test_is_exposable_for_uses_real_permission_path(auth_required_env):
    """Smoke-test that the policy reaches ``user_has_permission``
    through the same Supabase mock path the existing permission tests
    use, so the asymmetry from NBB-202A flows through verbatim."""
    with patch.object(permissions, "_get_supabase") as mock_get:
        # User row with chat_features.memory disabled.
        stored = {
            "chat_features": {"enabled": True, "items": {"memory": False}},
        }
        mock_get.return_value = _stub_supabase_response(stored)

        assert tool_capability_policy.is_exposable_for(
            "user-1", "store_memory"
        ) is False


def test_is_exposable_for_preserves_db_failure_fail_closed(auth_required_env):
    """NBB-202A intentional asymmetry: ``user_has_permission``
    re-queries on a permission check and fails closed on DB error.
    The policy must inherit that behavior."""
    with patch.object(
        permissions, "_get_supabase", side_effect=Exception("db down")
    ):
        assert tool_capability_policy.is_exposable_for(
            "user-1", "studio_signal"
        ) is False


def test_is_exposable_for_allows_when_permission_granted(auth_required_env):
    with patch.object(permissions, "_get_supabase") as mock_get:
        # NULL permissions = apply DEFAULT_PERMISSIONS (all enabled).
        mock_get.return_value = _stub_supabase_response(None)

        assert tool_capability_policy.is_exposable_for(
            "user-1", "search_sources"
        ) is True
