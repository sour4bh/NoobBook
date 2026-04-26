"""
Architecture checks for the NoobBook structure migration (NBB-704A + NBB-704B).

NBB-704A established two narrow rules that hold long before migration finishes:

1. Backend root registry. Every top-level child of ``backend/app/`` must be a
   canonical root from ``STRUCTURE.md`` (NBB-104). Legacy roots (``services``,
   ``utils``) and the existing ``config`` package are tolerated as known
   migration state; new roots outside the approved list fail. This catches a
   contributor inventing a new mechanism bucket such as ``backend/app/agents/``.

2. Import direction at the external edge (NBB-104, NBB-206).
   - ``backend/app/providers/`` is a leaf. It must not import from ``app.api``,
     ``app.connectors``, or any domain root (``app.auth``, ``app.projects``,
     ``app.chat``, ``app.sources``, ``app.studio``, ``app.brand``,
     ``app.background``, ``app.settings``).
   - ``backend/app/connectors/`` may import from ``app.providers``,
     ``app.auth``, and ``app.projects`` (per ``connectors/CHARTER.md``); it
     must not import from ``app.api`` or from the other domain roots.

NBB-704B adds richer post-migration boundary checks now that domains exist:

3. Documented inherited-violation allowlist (path a). The five providers→domain
   imports that landed when ``utils/cost_tracking.py`` and ``utils/embedding_utils``
   moved under ``providers/anthropic/`` (NBB-705C) stay in place; cost tracking
   and API token counting are observability concerns that legitimately depend
   on user/project/chat ownership, and the lazy imports already break the
   providers→domain runtime cycle. Each entry is encoded as
   ``(rel_path, lineno, target_root)`` so a re-fire on a different line still
   surfaces. See ``providers/CHARTER.md`` "Documented exceptions (NBB-704B)"
   for the per-line rationale.

4. Chat publics-only rule. Code outside ``app.chat/`` must reach chat through
   the public surface declared in ``app.chat.__all__`` ({store, tools, schemas,
   send, stream, ChatEvent, ChatResponse}). Reaching deeper paths such as
   ``app.chat.message.store`` is rejected; callers that need message
   persistence import ``message_service`` from ``app.chat.store``.

5. Inter-domain regression guard. ``app.auth/``, ``app.projects/``,
   ``app.connectors/``, ``app.brand/``, ``app.background/``, and ``app.settings/``
   currently do not import from ``app.chat``, ``app.sources``, or ``app.studio``
   at all (one allowlisted registry exception: ``auth/tool_policy.py`` lazily
   imports ``sources.analysis.tool_capabilities`` for cross-cutting capability
   registration owned by NBB-202B). Lock the property — these roots may not
   depend on the migrated domains in either direction, today or in future
   commits.

The stateless-singleton and type safety checks are owned by NBB-704C. The
sources/studio public-surface enforcement and the frontend ownership check are
intentionally deferred (see ``backend/STRUCTURE.md`` Architecture checks). This
script stays stdlib-only by design.

Usage:
    python backend/scripts/verify_architecture.py

Exits 0 when no violations are found. Exits 1 and prints one line per offense.
"""
import ast
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
REPO_ROOT = BACKEND_DIR.parent

# Canonical backend roots from STRUCTURE.md (NBB-104). Every backend file
# belongs under one of these.
CANONICAL_ROOTS: frozenset[str] = frozenset({
    "api",
    "auth",
    "projects",
    "chat",
    "sources",
    "studio",
    "brand",
    "settings",
    "connectors",
    "providers",
    "background",
    "base",
})

# Domain roots. Used for import-direction checks at the external edge.
DOMAIN_ROOTS: frozenset[str] = frozenset({
    "auth",
    "projects",
    "chat",
    "sources",
    "studio",
    "brand",
    "background",
    "settings",
})

# Legacy roots NBB-103 still allows to read from during the migration. New
# files under these are blocked by ``scripts/ci/check_no_new_legacy_files.py``;
# this script tolerates their continued existence so the root-registry check
# does not fire on the migration's current state.
LEGACY_ROOTS: frozenset[str] = frozenset({
    "services",
    "utils",
})

# Non-canonical roots tolerated for reasons tracked elsewhere. ``config`` is
# the ``backend/config.py`` vs ``backend/app/config/`` name-collision noted in
# the sprint Blocker Log; its structural fix is flagged for a follow-up
# ticket, not NBB-704A.
TOLERATED_ROOTS: frozenset[str] = frozenset({
    "config",
})

# providers/ is a leaf; it must not depend on api, connectors, or any domain.
PROVIDERS_FORBIDDEN_PREFIXES: Tuple[str, ...] = tuple(
    sorted({"api", "connectors"} | set(DOMAIN_ROOTS))
)

# connectors/ may depend on providers, auth, and projects (per CHARTER.md).
# Anything else under app. is a boundary violation.
CONNECTORS_ALLOWED_PREFIXES: frozenset[str] = frozenset({
    "providers",
    "auth",
    "projects",
})
CONNECTORS_FORBIDDEN_PREFIXES: Tuple[str, ...] = tuple(
    sorted(
        ({"api"} | set(DOMAIN_ROOTS)) - CONNECTORS_ALLOWED_PREFIXES
    )
)

# NBB-704B path (a): inherited providers→domain imports that landed with
# NBB-705C (cost_tracking + embedding_utils drain). Each entry is
# ``(rel_path, lineno, target_root)`` so a future re-fire on a different line
# still surfaces. Rationale lives in ``providers/CHARTER.md``
# "Documented exceptions (NBB-704B)" — observability legitimately depends on
# user/project/chat ownership, and the lazy imports already break the
# providers→domain runtime cycle.
INHERITED_PROVIDER_VIOLATIONS: frozenset[Tuple[str, int, str]] = frozenset({
    ("backend/app/providers/anthropic/cost.py", 76, "projects"),
    ("backend/app/providers/anthropic/cost.py", 82, "chat"),
    ("backend/app/providers/anthropic/cost.py", 300, "auth"),
    ("backend/app/providers/anthropic/cost.py", 357, "auth"),
    ("backend/app/providers/anthropic/token_count.py", 12, "sources"),
})

# NBB-704B rule 4: chat public surface, derived from ``app.chat.__all__``.
# A non-chat caller must reach chat via these submodules; any deeper path
# (``app.chat.message.store``, ``app.chat.loop``, ``app.chat.tool.policy``,
# etc.) is a boundary violation.
CHAT_PUBLIC_SUBMODULES: frozenset[str] = frozenset({
    "store",
    "tools",
    "schemas",
})

# NBB-704B rule 5: roots that currently have zero cross-domain imports into
# ``app.chat``, ``app.sources``, or ``app.studio``. Lock that property as a
# regression guard — these roots stay independent of the migrated domains.
INDEPENDENT_ROOTS: Tuple[str, ...] = (
    "auth",
    "projects",
    "connectors",
    "brand",
    "background",
    "settings",
)
MIGRATED_DOMAINS: Tuple[str, ...] = ("chat", "sources", "studio")

# NBB-704B rule 5 inherited exception: ``auth.tool_policy`` runs a lazy
# registry-loading import of ``app.sources.analysis.tool_capabilities`` to
# attach sources-owned tool capabilities to the policy registry it owns
# (NBB-202B). The import is gated behind ``_ensure_loaded`` to avoid the
# providers→domain runtime cycle and the source side reciprocally imports
# from ``app.auth.tool_policy``. This is a known cross-cutting registry
# pattern, not a regression.
INDEPENDENT_ROOTS_ALLOWLIST: frozenset[Tuple[str, int, str]] = frozenset({
    ("backend/app/auth/tool_policy.py", 225, "sources"),
})


class Violation:
    __slots__ = ("path", "lineno", "message")

    def __init__(self, path: Optional[Path], lineno: int, message: str) -> None:
        self.path = path
        self.lineno = lineno
        self.message = message

    def format(self) -> str:
        if self.path is None:
            return f"{self.message}"
        rel = self.path.relative_to(REPO_ROOT)
        if self.lineno > 0:
            return f"{rel}:{self.lineno}: {self.message}"
        return f"{rel}: {self.message}"


def check_root_registry() -> List[Violation]:
    """Flag top-level children of ``backend/app/`` outside the approved set."""
    approved = CANONICAL_ROOTS | LEGACY_ROOTS | TOLERATED_ROOTS
    violations: List[Violation] = []
    for entry in sorted(APP_DIR.iterdir()):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_file() and entry.suffix != ".py":
            continue
        if entry.is_file() and entry.name == "__init__.py":
            continue
        # Module names are directories or top-level .py files.
        name = entry.stem if entry.is_file() else entry.name
        if name in approved:
            continue
        kind = "module" if entry.is_file() else "package"
        violations.append(Violation(
            entry,
            0,
            (
                f"new backend root {kind} '{name}' is not in the canonical "
                "root list from STRUCTURE.md (NBB-104). Add the file under an "
                "approved domain root instead."
            ),
        ))
    return violations


def _app_import_root(module: Optional[str]) -> Optional[str]:
    """Return the first segment after ``app.`` for ``app.<root>.<...>`` modules.

    Returns ``None`` for relative imports, non-``app`` imports, or bare ``app``.
    """
    if not module:
        return None
    parts = module.split(".")
    if parts[0] != "app" or len(parts) < 2:
        return None
    return parts[1]


def _iter_import_roots(tree: ast.AST) -> Iterable[Tuple[int, str]]:
    """Yield ``(lineno, root)`` for every absolute ``app.<root>`` import."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Relative imports have ``level > 0``; they stay inside the package
            # and are not import-direction violations.
            if node.level and node.level > 0:
                continue
            root = _app_import_root(node.module)
            if root is not None:
                yield node.lineno, root
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = _app_import_root(alias.name)
                if root is not None:
                    yield node.lineno, root


def _iter_import_modules(tree: ast.AST) -> Iterable[Tuple[int, str]]:
    """Yield ``(lineno, module)`` for every absolute ``app.*`` import.

    Distinct from ``_iter_import_roots``: this returns the full dotted module
    path (e.g. ``app.chat.message.store``) so callers can reason about reach
    into a domain's internals, not just the top-level root.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            module = node.module
            if module and module.split(".")[0] == "app":
                yield node.lineno, module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "app":
                    yield node.lineno, alias.name


def _rel_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _check_package_imports(
    package_dir: Path,
    forbidden_prefixes: Tuple[str, ...],
    package_label: str,
    allowlist: frozenset = frozenset(),
) -> List[Violation]:
    """Flag absolute ``app.<forbidden>`` imports inside ``package_dir``.

    ``allowlist`` is a set of ``(rel_path, lineno, target_root)`` tuples that
    suppresses individual matches without widening the rule. NBB-704A used the
    rule with no allowlist; NBB-704B passes the inherited providers→domain
    allowlist for the five lines documented in ``providers/CHARTER.md``.
    """
    violations: List[Violation] = []
    if not package_dir.is_dir():
        return violations
    for path in sorted(package_dir.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(Violation(path, 0, f"cannot read file: {exc}"))
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(Violation(path, exc.lineno or 0, f"syntax error: {exc.msg}"))
            continue
        rel = _rel_path(path)
        for lineno, root in _iter_import_roots(tree):
            if root not in forbidden_prefixes:
                continue
            if (rel, lineno, root) in allowlist:
                continue
            violations.append(Violation(
                path,
                lineno,
                (
                    f"{package_label} must not import from 'app.{root}' "
                    "(see STRUCTURE.md Dependency Direction + "
                    f"{package_label}/CHARTER.md)."
                ),
            ))
    return violations


def check_providers_imports() -> List[Violation]:
    return _check_package_imports(
        APP_DIR / "providers",
        PROVIDERS_FORBIDDEN_PREFIXES,
        "providers",
        allowlist=INHERITED_PROVIDER_VIOLATIONS,
    )


def check_connectors_imports() -> List[Violation]:
    return _check_package_imports(
        APP_DIR / "connectors",
        CONNECTORS_FORBIDDEN_PREFIXES,
        "connectors",
    )


def _is_under(path: Path, root_name: str) -> bool:
    """True when ``path`` lives under ``backend/app/<root_name>/``."""
    target = APP_DIR / root_name
    try:
        path.relative_to(target)
    except ValueError:
        return False
    return True


def check_chat_publics_only() -> List[Violation]:
    """NBB-704B rule 4. Outside ``app.chat/``, only chat publics are allowed.

    The chat public surface is ``app.chat`` itself plus the submodules listed
    in ``app.chat.__all__``. Any deeper path (``app.chat.message.store``,
    ``app.chat.loop``, ``app.chat.tool.policy``, ...) is a reach into chat
    internals.
    """
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if _is_under(path, "chat"):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(Violation(path, 0, f"cannot read file: {exc}"))
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(Violation(path, exc.lineno or 0, f"syntax error: {exc.msg}"))
            continue
        for lineno, module in _iter_import_modules(tree):
            parts = module.split(".")
            if len(parts) < 2 or parts[1] != "chat":
                continue
            # ``app.chat`` (root) and ``app.chat.<public>`` are allowed.
            if len(parts) == 2:
                continue
            second = parts[2]
            if second in CHAT_PUBLIC_SUBMODULES:
                continue
            violations.append(Violation(
                path,
                lineno,
                (
                    f"reaches into chat internals via '{module}'. Use the "
                    "chat public surface (app.chat / app.chat.store / "
                    "app.chat.tools / app.chat.schemas) per chat/__init__.py "
                    "and chat/CHARTER.md (NBB-704B)."
                ),
            ))
    return violations


def check_independent_roots() -> List[Violation]:
    """NBB-704B rule 5. Independent roots stay independent of migrated domains.

    Locks the empirically-zero state at base commit f118268: ``app.auth``,
    ``app.projects``, ``app.connectors``, ``app.brand``, ``app.background``,
    and ``app.settings`` do not import from ``app.chat``, ``app.sources``, or
    ``app.studio``. Any future regression fires here with no allowlist —
    these roots have no inherited cross-domain debt to absorb.
    """
    violations: List[Violation] = []
    for root_name in INDEPENDENT_ROOTS:
        root_dir = APP_DIR / root_name
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.py")):
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                violations.append(Violation(path, 0, f"cannot read file: {exc}"))
                continue
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError as exc:
                violations.append(Violation(path, exc.lineno or 0, f"syntax error: {exc.msg}"))
                continue
            rel = _rel_path(path)
            for lineno, root in _iter_import_roots(tree):
                if root not in MIGRATED_DOMAINS:
                    continue
                if (rel, lineno, root) in INDEPENDENT_ROOTS_ALLOWLIST:
                    continue
                violations.append(Violation(
                    path,
                    lineno,
                    (
                        f"'{root_name}' must not import from migrated domain "
                        f"'app.{root}'. The independence is locked at base "
                        "commit f118268 by NBB-704B."
                    ),
                ))
    return violations


def main() -> int:
    if not APP_DIR.is_dir():
        sys.stderr.write(f"error: {APP_DIR} not found\n")
        return 2

    violations: List[Violation] = []
    violations.extend(check_root_registry())
    violations.extend(check_providers_imports())
    violations.extend(check_connectors_imports())
    violations.extend(check_chat_publics_only())
    violations.extend(check_independent_roots())

    if violations:
        for v in violations:
            print(v.format())
        print(f"{len(violations)} architecture violation(s)")
        return 1

    print("0 architecture violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
