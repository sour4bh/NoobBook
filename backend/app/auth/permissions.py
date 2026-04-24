"""
Per-user module permissions.

Permission taxonomy (five categories, each with an ``enabled`` master
toggle and an ``items`` dict of sub-item booleans):

- ``document_sources`` — PDF, DOCX, PPTX, Image, Audio, URL/YouTube,
  Text, Google Drive.
- ``data_sources`` — Database, CSV, Freshdesk, Jira, Mixpanel (the
  sensitive data-access side; overlaps on purpose with ``integrations``
  for Jira/Mixpanel because some flows only need the credentials and
  others ingest actual source rows).
- ``studio`` — every content-generation item in the studio taxonomy.
- ``integrations`` — Jira, Mixpanel, Notion, MCP, ElevenLabs (credential
  wiring and connector features).
- ``chat_features`` — Memory, Voice Input, Chat Export.

Storage and policy:

- ``users.permissions`` is a JSONB column; ``NULL`` means "apply
  ``DEFAULT_PERMISSIONS``" so a fresh user does not need 50+ rows
  written on insert.
- ``DEFAULT_PERMISSIONS`` is all-enabled and is also returned verbatim
  to the frontend for admins (`/settings/users/me/permissions`) and for
  API-response shape generation.
- Permission checks are **fail-closed** in auth-required mode
  (``NOOBBOOK_AUTH_REQUIRED`` unset or truthy). Unknown categories,
  unknown items, and Supabase failures all deny. The only allow-on-miss
  branch is ``NOOBBOOK_AUTH_REQUIRED=false`` (dev/single-user) — that
  mode keeps the historical "default to allow" behavior but does so
  through named helpers (``_fallback_allow``) so the code path is
  explicit rather than silent.
- The frontend ``PermissionsContext`` defaults to allow during load /
  on error; that is UI-only convenience. The backend never trusts a
  frontend-asserted permission.
"""

import logging
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed taxonomy
# ---------------------------------------------------------------------------

# The canonical set of categories and the items each one owns. Declared
# as a plain module-level mapping so consumers can treat it as the
# source of truth for "what does this category mean?" without pulling
# in enum machinery. ``DEFAULT_PERMISSIONS`` is derived from this so the
# two stay in lockstep.
PERMISSION_TAXONOMY: Mapping[str, frozenset] = {
    "document_sources": frozenset({
        "pdf",
        "docx",
        "pptx",
        "image",
        "audio",
        "url_youtube",
        "text",
        "google_drive",
    }),
    "data_sources": frozenset({
        "database",
        "csv",
        "freshdesk",
        "jira",
        "mixpanel",
    }),
    "studio": frozenset({
        "audio_overview",
        "ad_creative",
        "flash_cards",
        "flow_diagrams",
        "infographics",
        "mind_maps",
        "quizzes",
        "social_posts",
        "emails",
        "websites",
        "components",
        "videos",
        "wireframes",
        "presentations",
        "prds",
        "marketing_strategies",
        "blogs",
        "business_reports",
    }),
    "integrations": frozenset({
        "jira",
        "mixpanel",
        "notion",
        "mcp",
        "elevenlabs",
    }),
    "chat_features": frozenset({
        "memory",
        "voice_input",
        "chat_export",
    }),
}

KNOWN_CATEGORIES: frozenset = frozenset(PERMISSION_TAXONOMY.keys())


def is_known_category(category: str) -> bool:
    """Return True if ``category`` is part of the declared taxonomy."""
    return category in KNOWN_CATEGORIES


def is_known_item(category: str, item: str) -> bool:
    """Return True if ``item`` is declared under ``category``.

    Returns False when the category itself is unknown; callers that
    care about that distinction should check ``is_known_category``
    first.
    """
    items = PERMISSION_TAXONOMY.get(category)
    if items is None:
        return False
    return item in items


def _get_default_permissions() -> Dict[str, Any]:
    """Return the all-enabled permission structure.

    Built from ``PERMISSION_TAXONOMY`` so adding a new item in one
    place automatically enables it by default for fresh users.
    """
    return {
        category: {
            "enabled": True,
            "items": {item: True for item in items},
        }
        for category, items in PERMISSION_TAXONOMY.items()
    }


# Exported constant for API responses and frontend type generation.
# Consumers treat this as read-only; rebuild via
# ``_get_default_permissions()`` if a fresh copy is needed.
DEFAULT_PERMISSIONS = _get_default_permissions()


# ---------------------------------------------------------------------------
# Mode helpers
# ---------------------------------------------------------------------------


def _fallback_allow() -> bool:
    """Return the answer ``user_has_permission`` should give when it
    cannot prove a decision from data.

    In auth-required mode the answer is **deny** (False): unknown
    categories, unknown items, and DB failures must not quietly open
    production access. In dev / single-user mode
    (``NOOBBOOK_AUTH_REQUIRED=false``) the answer is **allow** (True)
    to keep local development frictionless; this is the only path that
    preserves the historical "default to allow" behavior.

    Imports ``is_auth_required`` lazily so this module can load before
    the Supabase client is configured (``app.auth.identity`` pulls in
    the Supabase provider at module load).
    """
    from app.auth.identity import is_auth_required

    return not is_auth_required()


# ---------------------------------------------------------------------------
# Supabase I/O
# ---------------------------------------------------------------------------


def _get_supabase():
    """Lazy import to avoid circular dependencies."""
    from app.services.integrations.supabase import get_supabase
    return get_supabase()


def get_user_permissions(user_id: str) -> Dict[str, Any]:
    """Load permissions for a user.

    Returns the stored JSONB merged with ``DEFAULT_PERMISSIONS`` when
    the row exists, or ``DEFAULT_PERMISSIONS`` when the row is missing
    or ``permissions`` is NULL. A Supabase exception falls back to
    ``DEFAULT_PERMISSIONS`` with a logged warning — callers that need
    fail-closed semantics go through ``user_has_permission``, which
    treats DB failure as deny in auth-required mode.

    This function is also used by the admin permissions UI to
    pre-populate toggles, so it must return a well-shaped dict rather
    than raise.
    """
    try:
        client = _get_supabase()
        response = (
            client.table("users")
            .select("permissions")
            .eq("id", user_id)
            .execute()
        )
        if not response.data:
            return _get_default_permissions()

        stored = response.data[0].get("permissions")
        if stored is None:
            return _get_default_permissions()

        # Merge with defaults so items added to the taxonomy after the
        # user's row was last written are automatically enabled.
        return _merge_with_defaults(stored, _get_default_permissions())
    except Exception as e:
        logger.error("Failed to load permissions for user %s: %s", user_id, e)
        return _get_default_permissions()


def _merge_with_defaults(stored: Dict, defaults: Dict) -> Dict:
    """Merge stored permissions with defaults.

    Any category or item declared in ``PERMISSION_TAXONOMY`` that is
    not in ``stored`` uses the default value. Unknown keys in
    ``stored`` are dropped — the taxonomy is the source of truth for
    what the API exposes.
    """
    merged = {}
    for category, default_cat in defaults.items():
        if category not in stored:
            merged[category] = default_cat
            continue

        stored_cat = stored[category]
        merged[category] = {
            "enabled": stored_cat.get("enabled", default_cat["enabled"]),
            "items": {},
        }

        for item, default_val in default_cat["items"].items():
            stored_items = stored_cat.get("items", {})
            merged[category]["items"][item] = stored_items.get(item, default_val)

    return merged


def update_user_permissions(user_id: str, permissions: Dict[str, Any]) -> bool:
    """Save customized permissions to the users table.

    Returns True on a successful write, False on error. Callers that
    need to enforce the admin-only contract do it at the route layer
    via ``require_admin``.
    """
    try:
        client = _get_supabase()
        response = (
            client.table("users")
            .update({"permissions": permissions})
            .eq("id", user_id)
            .execute()
        )
        return bool(response.data)
    except Exception as e:
        logger.error("Failed to update permissions for user %s: %s", user_id, e)
        return False


# ---------------------------------------------------------------------------
# Permission check
# ---------------------------------------------------------------------------


def user_has_permission(
    user_id: str, category: str, item: Optional[str] = None
) -> bool:
    """Return True if the user is allowed to use ``category`` / ``item``.

    Decision rules (in order):

    1. Unknown ``category`` -> ``_fallback_allow()``. Deny in
       auth-required mode; allow in dev/single-user.
    2. ``item`` supplied but unknown in that category ->
       ``_fallback_allow()``. Same reasoning.
    3. Load the user's permissions. If the DB read raises, deny in
       auth-required mode (``_fallback_allow()``) and log a warning;
       in dev/single-user mode fall back to ``DEFAULT_PERMISSIONS``
       so local development stays frictionless.
    4. If the category's ``enabled`` flag is False, deny.
    5. If no item was requested, allow (the category-level toggle
       passed).
    6. Return the item's stored boolean; default to the taxonomy
       default (True) if the item is missing from the stored row.

    ``require_permission`` in ``app.auth.guards`` turns ``False`` into
    a 403 response with the standard contact-admin message; callers
    that gate feature visibility inline (for example
    ``main_chat_service``) consume the bool directly.
    """
    # 1. Unknown category: do not silently allow in production.
    if not is_known_category(category):
        logger.warning(
            "user_has_permission called with unknown category %r (user=%s)",
            category,
            user_id,
        )
        return _fallback_allow()

    # 2. Unknown item under a known category: also fail-closed.
    if item is not None and not is_known_item(category, item):
        logger.warning(
            "user_has_permission called with unknown item %r in category %r "
            "(user=%s)",
            item,
            category,
            user_id,
        )
        return _fallback_allow()

    # 3. Load stored permissions. ``get_user_permissions`` swallows
    #    Supabase exceptions and returns defaults; to keep fail-closed
    #    semantics in auth-required mode we re-do the call here and
    #    handle failure explicitly.
    try:
        client = _get_supabase()
        response = (
            client.table("users")
            .select("permissions")
            .eq("id", user_id)
            .execute()
        )
    except Exception as e:
        logger.warning(
            "Permission lookup failed for user=%s category=%s item=%s: %s",
            user_id,
            category,
            item,
            e,
        )
        return _fallback_allow()

    if not response.data:
        # No users row: treat as "apply defaults" just like NULL.
        perms = _get_default_permissions()
    else:
        stored = response.data[0].get("permissions")
        if stored is None:
            perms = _get_default_permissions()
        else:
            perms = _merge_with_defaults(stored, _get_default_permissions())

    cat = perms.get(category)
    # ``cat`` cannot be missing here because we merged against defaults,
    # but keep the guard so a malformed merge result still fails closed.
    if cat is None:
        logger.warning(
            "Merged permissions missing known category %r (user=%s)",
            category,
            user_id,
        )
        return _fallback_allow()

    if not cat.get("enabled", True):
        return False

    if item is None:
        return True

    # Known item: trust the stored value, defaulting to True for
    # items introduced after the user's row was last written.
    return cat.get("items", {}).get(item, True)


# ---------------------------------------------------------------------------
# Per-connection access control (Database & MCP)
# ---------------------------------------------------------------------------

def get_all_connections() -> Dict[str, Any]:
    """
    Return all database and MCP connections for the admin permissions modal.

    Returns:
        {"databases": [{"id": "...", "name": "..."}], "mcp": [{"id": "...", "name": "..."}]}
    """
    try:
        client = _get_supabase()
        db_resp = client.table("database_connections").select("id, name").order("name").execute()
        mcp_resp = client.table("mcp_connections").select("id, name").order("name").execute()
        return {
            "databases": db_resp.data or [],
            "mcp": mcp_resp.data or [],
        }
    except Exception as e:
        logger.error("Failed to list connections: %s", e)
        return {"databases": [], "mcp": []}


def get_user_connection_access(user_id: str) -> Dict[str, list]:
    """
    Return which database and MCP connection IDs a user has access to.

    Educational Note: A user has access if:
    1. The connection has visible_to_all=true, OR
    2. The user is in the connection_users junction table

    For the permissions modal we simplify: return which connection IDs
    are in the junction table. The admin toggles add/remove from there.
    Connections with visible_to_all=true are shown as enabled by default.

    Returns:
        {"database_ids": ["uuid1", ...], "mcp_ids": ["uuid2", ...]}
    """
    try:
        client = _get_supabase()

        db_resp = (
            client.table("database_connection_users")
            .select("connection_id")
            .eq("user_id", user_id)
            .execute()
        )
        mcp_resp = (
            client.table("mcp_connection_users")
            .select("connection_id")
            .eq("user_id", user_id)
            .execute()
        )

        # Also include connections that are visible_to_all
        db_visible = (
            client.table("database_connections")
            .select("id")
            .eq("visible_to_all", True)
            .execute()
        )
        mcp_visible = (
            client.table("mcp_connections")
            .select("id")
            .eq("visible_to_all", True)
            .execute()
        )

        db_ids = set(r["connection_id"] for r in (db_resp.data or []))
        db_ids.update(r["id"] for r in (db_visible.data or []))

        mcp_ids = set(r["connection_id"] for r in (mcp_resp.data or []))
        mcp_ids.update(r["id"] for r in (mcp_visible.data or []))

        return {
            "database_ids": list(db_ids),
            "mcp_ids": list(mcp_ids),
        }
    except Exception as e:
        logger.error("Failed to get connection access for %s: %s", user_id, e)
        return {"database_ids": [], "mcp_ids": []}


def update_user_connection_access(
    user_id: str,
    database_ids: Optional[list] = None,
    mcp_ids: Optional[list] = None,
) -> bool:
    """
    Set which database and MCP connections a user can access.

    Educational Note: This replaces the user's entries in the junction tables.
    Connections with visible_to_all=true remain accessible regardless.
    The admin uses this to restrict access to specific connections.
    """
    try:
        client = _get_supabase()

        if database_ids is not None:
            # Clear existing entries
            client.table("database_connection_users").delete().eq("user_id", user_id).execute()
            # Insert new entries
            for conn_id in database_ids:
                client.table("database_connection_users").insert({
                    "connection_id": conn_id,
                    "user_id": user_id,
                }).execute()

        if mcp_ids is not None:
            client.table("mcp_connection_users").delete().eq("user_id", user_id).execute()
            for conn_id in mcp_ids:
                client.table("mcp_connection_users").insert({
                    "connection_id": conn_id,
                    "user_id": user_id,
                }).execute()

        return True
    except Exception as e:
        logger.error("Failed to update connection access for %s: %s", user_id, e)
        return False
