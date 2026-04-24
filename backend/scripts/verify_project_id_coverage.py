"""
Verify every call that resolves to ``claude_service.send_message`` (or
``claude_service.stream_message``) passes ``project_id`` so per-project cost
tracking stays complete.

Usage:
    python scripts/verify_project_id_coverage.py

Exits 0 with ``0 omissions`` when every call site is covered. Exits non-zero
and prints each offending call when any omission is found.

Coverage rules:
- Import aliasing is resolved at AST level. All of the following point at the
  singleton and count:
    from app.services.integrations.claude import claude_service
    from app.services.integrations.claude import claude_service as X
    from app.services.integrations.claude.claude_service import claude_service
    import app.services.integrations.claude as X  (X.claude_service.send_message)
- ``claude_service.send_message(**kwargs)`` is treated as forwarding and passes
  so long as a ``**kwargs`` double-star is present. The verifier assumes the
  caller forwards ``project_id`` through that kwargs map — this is the pattern
  used by ``main_chat_service._call_claude``.
- A call that passes ``project_id=...`` explicitly (including ``project_id=None``)
  counts as covered. Cost tracking in ``claude_service.send_message`` already
  treats falsy ``project_id`` as a logged skip.
"""
import ast
import sys
from pathlib import Path
from typing import List, Set, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"

CLAUDE_MODULE = "app.services.integrations.claude"
CLAUDE_SUBMODULE = "app.services.integrations.claude.claude_service"
SINGLETON_NAME = "claude_service"
TARGET_METHODS = frozenset({"send_message", "stream_message"})


class Omission:
    __slots__ = ("path", "lineno", "col", "receiver", "method", "reason")

    def __init__(
        self,
        path: Path,
        lineno: int,
        col: int,
        receiver: str,
        method: str,
        reason: str,
    ) -> None:
        self.path = path
        self.lineno = lineno
        self.col = col
        self.receiver = receiver
        self.method = method
        self.reason = reason

    def format(self, root: Path) -> str:
        rel = self.path.relative_to(root)
        return (
            f"{rel}:{self.lineno}:{self.col} "
            f"{self.receiver}.{self.method}() - {self.reason}"
        )


def _module_aliases(tree: ast.AST) -> Tuple[Set[str], Set[str]]:
    """
    Scan a module's top-level imports.

    Returns:
        singleton_names: identifiers bound directly to the ``claude_service``
            singleton (e.g. ``claude_service``, ``cs``).
        module_names: identifiers bound to the containing module (e.g.
            ``import app.services.integrations.claude as cm``). Attribute
            access ``cm.claude_service.send_message(...)`` resolves through
            these.
    """
    singletons: Set[str] = set()
    modules: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == CLAUDE_MODULE or mod == CLAUDE_SUBMODULE:
                for alias in node.names:
                    if alias.name == SINGLETON_NAME:
                        singletons.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in (CLAUDE_MODULE, CLAUDE_SUBMODULE):
                    # Only the leaf of an aliased import is a new binding; a
                    # plain `import a.b.c` exposes `a` at the usage site.
                    bind = alias.asname or alias.name.split(".")[0]
                    modules.add(bind)

    return singletons, modules


def _is_send_call_receiver(
    func: ast.expr,
    singleton_names: Set[str],
    module_names: Set[str],
) -> Tuple[bool, str, str]:
    """
    Decide if ``func`` is ``<singleton>.send_message`` / ``stream_message``
    (the targets we track). Returns (is_target, receiver_repr, method).
    """
    if not isinstance(func, ast.Attribute):
        return False, "", ""
    if func.attr not in TARGET_METHODS:
        return False, "", ""

    value = func.value

    # Case 1: singleton.send_message(...)
    if isinstance(value, ast.Name) and value.id in singleton_names:
        return True, value.id, func.attr

    # Case 2: module.claude_service.send_message(...)
    if (
        isinstance(value, ast.Attribute)
        and value.attr == SINGLETON_NAME
        and isinstance(value.value, ast.Name)
        and value.value.id in module_names
    ):
        return True, f"{value.value.id}.{SINGLETON_NAME}", func.attr

    return False, "", ""


def _covers_project_id(call: ast.Call) -> Tuple[bool, str]:
    """Return (covered, reason). ``reason`` is empty when covered."""
    # Double-star forwarding (e.g. ``send_message(**kwargs)``) is treated as a
    # legitimate wrapper. ``main_chat_service._call_claude`` uses this pattern.
    for kw in call.keywords:
        if kw.arg is None:
            return True, ""
    for kw in call.keywords:
        if kw.arg == "project_id":
            return True, ""
    return False, "missing project_id keyword argument"


def scan_file(path: Path) -> List[Omission]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise SystemExit(f"syntax error in {path}: {exc}")

    singletons, modules = _module_aliases(tree)
    if not singletons and not modules:
        return []

    omissions: List[Omission] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_target, receiver, method = _is_send_call_receiver(
            node.func, singletons, modules
        )
        if not is_target:
            continue
        covered, reason = _covers_project_id(node)
        if covered:
            continue
        omissions.append(
            Omission(
                path=path,
                lineno=node.lineno,
                col=node.col_offset,
                receiver=receiver,
                method=method,
                reason=reason,
            )
        )
    return omissions


def main() -> int:
    if not APP_DIR.is_dir():
        print(f"error: {APP_DIR} not found", file=sys.stderr)
        return 2

    all_omissions: List[Omission] = []
    scanned = 0
    for path in sorted(APP_DIR.rglob("*.py")):
        scanned += 1
        all_omissions.extend(scan_file(path))

    if all_omissions:
        for omission in all_omissions:
            print(omission.format(BACKEND_DIR))
        print(f"{len(all_omissions)} omissions across {scanned} files")
        return 1

    print(f"0 omissions across {scanned} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
