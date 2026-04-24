"""
Early architecture checks for the NoobBook structure migration (NBB-704A).

Enforces two narrow rules that should hold long before the migration finishes:

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

The rich post-migration import-boundary coverage is owned by NBB-704B. The
stateless-singleton and type safety checks are owned by NBB-704C. This script
stays broad and stdlib-only by design.

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


def _check_package_imports(
    package_dir: Path,
    forbidden_prefixes: Tuple[str, ...],
    package_label: str,
) -> List[Violation]:
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
        for lineno, root in _iter_import_roots(tree):
            if root in forbidden_prefixes:
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
    )


def check_connectors_imports() -> List[Violation]:
    return _check_package_imports(
        APP_DIR / "connectors",
        CONNECTORS_FORBIDDEN_PREFIXES,
        "connectors",
    )


def main() -> int:
    if not APP_DIR.is_dir():
        sys.stderr.write(f"error: {APP_DIR} not found\n")
        return 2

    violations: List[Violation] = []
    violations.extend(check_root_registry())
    violations.extend(check_providers_imports())
    violations.extend(check_connectors_imports())

    if violations:
        for v in violations:
            print(v.format())
        print(f"{len(violations)} architecture violation(s)")
        return 1

    print("0 architecture violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
