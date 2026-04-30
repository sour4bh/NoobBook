"""
Tool capability policy for model-visible tools.

Every tool exposed to the model must declare a ``ToolCapability`` entry. The
policy enforces three things:

1. Unclassified tools are never exposable. ``is_exposable_for`` returns
   ``False`` for any tool without an entry, which is what makes
   "analysis tools cannot be exposed without capability classification"
   testable rather than aspirational.
2. Capability-aware exposure honors the NBB-202A fail-closed contract.
   In auth-required mode a missing ``user_id`` denies; in dev /
   single-user mode (``NOOBBOOK_AUTH_REQUIRED=false``) a missing
   ``user_id`` allows. Asymmetry between ``get_user_permissions`` and
   ``user_has_permission`` is preserved by routing decisions through
   ``user_has_permission``.
3. Required permission is encoded as a ``(category, item)`` pair from
   the NBB-202A taxonomy. Items may be ``None`` (category-level toggle
   suffices); unknown categories or items still fail closed inside
   ``user_has_permission``.

The central classification list itself lives in
``app.auth.tool_capabilities``. Domain-owned tool families may register
additional entries from their own module, but the domain surface that exposes
those tools is responsible for importing that module so auth does not depend
on migrated product domains.

Connector entries (Jira/Notion/Mixpanel) currently live in the central
module. If a connector later needs ownership-local capability policy, the
connector or chat exposure surface can import that module explicitly.
"""
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Dict, Iterable, Optional


class CapabilityLevel(str, Enum):
    """How invasive a tool's effect is.

    ``READ_ONLY`` describes a tool that only reads data (search,
    schema fetch, list calls). ``WRITE_CAPABLE`` describes a tool that
    writes to a domain store under our control (memory, studio
    signals). ``DESTRUCTIVE`` is reserved for tools whose effects are
    irreversible or escape the boundary entirely (raw-code execution,
    external account mutation).
    """

    READ_ONLY = "read-only"
    WRITE_CAPABLE = "write-capable"
    DESTRUCTIVE = "destructive"


class ToolScope(str, Enum):
    """Whether the tool's authorization is per-project or per-user.

    Project-scoped tools require an active source/connection inside the
    project (search, jira, mixpanel). Global-scoped tools follow the
    user's permissions only (memory, studio_signal, notion).
    """

    PROJECT = "project"
    GLOBAL = "global"


@dataclass(frozen=True)
class RequiredPermission:
    """The NBB-202A permission a caller must hold.

    ``item`` is ``None`` when the category-level toggle is enough.
    """

    category: str
    item: Optional[str] = None


@dataclass(frozen=True)
class ToolCapability:
    """Capability classification for a single model-visible tool.

    The seven required fields mirror the ticket scope verbatim
    (owner, required permission, scope, capability level, external
    side effects, confirmation required, audit/logging).

    All fields are required at construction; the dataclass is frozen so
    a registered entry cannot drift after import. Adding a new tool
    means adding an entry — there are no default values that could
    quietly skip classification.
    """

    name: str
    owner: str
    required_permission: RequiredPermission
    scope: ToolScope
    level: CapabilityLevel
    external_side_effects: bool
    requires_user_confirmation: bool
    audit_log: bool


class ToolCapabilityPolicy:
    """Registry + decision surface for model-visible tools.

    Tools register at module import; ``ensure_capabilities_loaded``
    triggers those imports exactly once so the registry is populated
    before any caller asks ``is_exposable_for``. Callers that already
    know the registry is loaded (tests after explicit import, chat
    after app startup) may skip the loader.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, ToolCapability] = {}
        # Reentrant: ``ensure_capabilities_loaded`` holds the lock while
        # importing registration modules whose top-level code calls
        # ``register`` (which also acquires the lock) on the same thread.
        # A non-reentrant ``Lock`` would deadlock that path; ``sys.modules``
        # already serializes module init, so the lock here only protects
        # the ``_loaded`` flag and the entries dict against multi-thread
        # races.
        self._lock = RLock()
        self._loaded = False

    # ----- registration -------------------------------------------------

    def register(self, capability: ToolCapability) -> None:
        """Register a single capability entry.

        Re-registering a tool with the same name raises. Drift between
        a domain's classification and the central one would silently
        change a deny/allow decision, so we make the conflict loud.
        """
        with self._lock:
            existing = self._entries.get(capability.name)
            if existing is not None and existing != capability:
                raise ValueError(
                    f"ToolCapability {capability.name!r} re-registered with "
                    f"a different classification (existing={existing!r}, "
                    f"new={capability!r})"
                )
            self._entries[capability.name] = capability

    def register_many(self, capabilities: Iterable[ToolCapability]) -> None:
        """Register a batch of capabilities (small DRY helper)."""
        for capability in capabilities:
            self.register(capability)

    # ----- introspection -----------------------------------------------

    def get(self, tool_name: str) -> Optional[ToolCapability]:
        """Return the capability for ``tool_name`` or ``None``."""
        return self._entries.get(tool_name)

    def has(self, tool_name: str) -> bool:
        """Return True if ``tool_name`` is classified."""
        return tool_name in self._entries

    def all_names(self) -> frozenset:
        """Snapshot of every registered tool name (for tests)."""
        return frozenset(self._entries.keys())

    # ----- decision -----------------------------------------------------

    def is_exposable_for(
        self, user_id: Optional[str], tool_name: str
    ) -> bool:
        """Return True if the tool may be sent to the model for ``user_id``.

        Decision rules (in order):

        1. Unclassified tool -> deny. This is the load-bearing rule
           that makes "analysis tools cannot be exposed without
           capability classification" enforceable.
        2. ``user_id is None`` and auth-required mode -> deny. Closes
           the historical short-circuit where a missing identity
           bypassed permission checks. Mirrors ``user_has_permission``
           fail-closed semantics.
        3. ``user_id is None`` and dev / single-user mode -> allow.
           Keeps local development frictionless without exposing the
           bypass to production.
        4. With a real ``user_id`` -> ask
           ``permissions.user_has_permission``. Asymmetry from
           NBB-202A is preserved: that function re-queries Supabase
           and fails closed on DB error in auth-required mode.
        """
        capability = self._entries.get(tool_name)
        if capability is None:
            return False

        # Lazy imports keep this module load-light and avoid pulling
        # Supabase clients during test collection.
        from app.auth.identity import is_auth_required
        from app.auth.permissions import user_has_permission

        if not user_id:
            return not is_auth_required()

        return user_has_permission(
            user_id,
            capability.required_permission.category,
            capability.required_permission.item,
        )

    # ----- registry loader ---------------------------------------------

    def ensure_capabilities_loaded(self) -> None:
        """Trigger registration modules exactly once.

        Each registration module performs ``policy.register(...)`` calls
        at import. Importing them here keeps the dependency direction
        clean: the policy primitive does not know which entries exist;
        the entry modules know about the policy.
        """
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            # Side-effect import registers central auth-owned entries.
            import app.auth.tool_capabilities  # noqa: F401

            self._loaded = True


# Singleton consumed by chat selection and tests. Tests that need a
# fresh registry monkeypatch ``_entries`` / ``_loaded`` directly rather
# than swapping the singleton.
tool_capability_policy = ToolCapabilityPolicy()
