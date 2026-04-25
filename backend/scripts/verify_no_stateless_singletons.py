"""
Stateless-singleton AST check for the NoobBook structure migration (NBB-704C).

Acceptance criterion (from NBB-704C ticket body): "New stateless singleton
service/executor classes fail checks unless explicitly allowlisted with an
owning cleanup ticket." The class+singleton pattern this rule targets looks
like::

    class FooService:
        def __init__(self):
            pass

    foo_service = FooService()

When a class is both stateless (empty ``__init__`` after stripping a leading
docstring, or no ``__init__`` at all) and gets a single module-level
constructor-call assignment, the right shape is module-level functions, not a
class with a singleton instance. NBB-706 will convert the two flagged
conversion targets in the allowlist below; the remaining eight entries are
orchestration classes that stay class-shaped per NBB-706's "Keep-as-class"
list. New occurrences fire the rule.

Allowlist asymmetry vs. NBB-706's seven explicit conversion targets:

- Two of NBB-706's seven (``EmbeddingService``, ``VideoPromptService``) match
  this rule and are seeded here as conversion targets.
- Five of NBB-706's seven do not match this rule because they are not
  module-level (state in ``__init__``, wrappers, etc.):
  ``SupabaseClient`` (state ``_client``/``_initialized``), ``OpenAIService``
  (state ``_client``), ``SummaryService`` (state ``_prompt_config``), and the
  remaining two are wrapper modules that re-export rather than define a
  class+singleton in this AST shape. NBB-706 converts them semantically, not
  by this rule.
- Eight allowlist entries are orchestration classes called out in NBB-706's
  "Keep-as-class" list (chat orchestration, integration orchestration, and
  source/studio orchestration). They stay class-shaped; their allowlist
  entries are permanent unless a future ticket names them.

Detection rule (top-level definitions only):
- Walk ``tree.body`` (not ``ast.walk``); classes nested inside functions or
  methods are not module-level singletons.
- A class is a "stateless singleton candidate" when:
  - its name ends with ``Service`` or ``Executor`` (matched on the class's
    own name, never on a base class), AND
  - it defines an ``__init__`` whose body is empty after stripping a leading
    string-literal docstring (length 0 or single ``ast.Pass``) OR it defines
    no ``__init__`` at all (default ``__init__`` is implicitly empty).
- The same module has a top-level ``Assign`` of the form
  ``<name> = ClassName(...)`` where:
  - the target is a single ``ast.Name`` (tuple/attribute targets are skipped),
  - the call's ``func`` is an ``ast.Name`` resolving to a class defined
    above in the module body (attribute-call constructors are skipped to keep
    the rule narrow).
- ``AnnAssign`` of the same shape (``name: T = ClassName()``) is also
  inspected. The base scan at ``f3281a7`` finds none, but covering the case
  prevents an annotated singleton from slipping past.

Multi-target assigns (``x = y = ClassName()``) are skipped intentionally.

Allowlist key is ``(rel_path, class_name)`` — line numbers drift across
unrelated edits, but the file/class pair is stable. Same precedent as
``verify_architecture.py``'s ``INHERITED_PROVIDER_VIOLATIONS`` and
``CHAT_INTERNAL_REACH_ALLOWLIST``.

Usage:
    python backend/scripts/verify_no_stateless_singletons.py

Exits 0 when every detected candidate is allowlisted. Exits 1 with one human
readable line per offense when any new candidate appears.
"""
import ast
import sys
from pathlib import Path
from typing import List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
REPO_ROOT = BACKEND_DIR.parent

# Seeded baseline at base commit f3281a7 — verified by AST scan. Each entry is
# (rel_path, class_name); the comment names the singleton variable plus the
# NBB-706 disposition (CONVERSION-TARGET vs KEEP-AS-CLASS).
ALLOWLIST: frozenset[Tuple[str, str]] = frozenset({
    # CONVERSION-TARGETS — NBB-706 deleted both AST-detected classes
    # (EmbeddingService, VideoPromptService) and dropped their allowlist
    # entries in the same commit as each conversion. No conversion targets
    # remain in this allowlist.

    # KEEP-AS-CLASS — orchestration classes per NBB-706's Keep-as-class list.
    # The allowlist entry stays unless a future ticket names a specific
    # stateless conversion.
    # Chat orchestration (memory_executor lives inside the chat domain).
    ("backend/app/chat/memory/store.py", "MemoryExecutor"),
    # Integration orchestration (Freshdesk sync lifecycle).
    ("backend/app/services/integrations/freshdesk/freshdesk_sync_service.py", "FreshdeskSyncService"),
    # Integration orchestration (MCP tool registry/lifecycle).
    ("backend/app/services/integrations/mcp/mcp_tool_service.py", "McpToolService"),
    # Source orchestration — NBB-403 lane (CSV analysis tool runtime).
    ("backend/app/sources/analysis/csv/tool.py", "CSVToolExecutor"),
    # Source orchestration (deep research agent runtime).
    ("backend/app/sources/analysis/research/tool.py", "DeepResearchExecutor"),
    # Source orchestration (web agent runtime for link sources).
    ("backend/app/sources/link/run.py", "WebAgentExecutor"),
    # Source orchestration (hybrid keyword+semantic search runtime).
    ("backend/app/sources/search.py", "SourceSearchExecutor"),
    # Studio orchestration (signal emission/ack runtime).
    ("backend/app/studio/signal.py", "StudioSignalExecutor"),
})


class Offense:
    __slots__ = ("path", "lineno", "class_name", "singleton_name")

    def __init__(self, path: Path, lineno: int, class_name: str, singleton_name: str) -> None:
        self.path = path
        self.lineno = lineno
        self.class_name = class_name
        self.singleton_name = singleton_name

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)
        return (
            f"{rel}:{self.lineno}: {rel.name}::{self.class_name} -> "
            f"{self.singleton_name} is a new stateless *Service/*Executor "
            "singleton. Convert to module-level functions, or add the entry to "
            "the allowlist in verify_no_stateless_singletons.py with a NBB-706 "
            "disposition (CONVERSION-TARGET or KEEP-AS-CLASS) and a one-line "
            "rationale."
        )


def _has_only_docstring_or_pass(body: List[ast.stmt]) -> bool:
    """Return True when ``body`` is empty after stripping a leading docstring.

    Empty body, single ``Pass``, single string-literal docstring, or docstring
    + ``Pass`` all count as empty. Anything else (assignments to ``self``,
    method calls, etc.) is real state.
    """
    stripped = list(body)
    if (
        stripped
        and isinstance(stripped[0], ast.Expr)
        and isinstance(stripped[0].value, ast.Constant)
        and isinstance(stripped[0].value.value, str)
    ):
        stripped = stripped[1:]
    if not stripped:
        return True
    if len(stripped) == 1 and isinstance(stripped[0], ast.Pass):
        return True
    return False


def _is_stateless_class(node: ast.ClassDef) -> bool:
    """Match on the class's own name suffix and an empty ``__init__``.

    Inheriting from a class named ``Service`` does not count — the rule is
    about the class's own naming pattern, per NBB-704C dispatch edge case.
    """
    if not (node.name.endswith("Service") or node.name.endswith("Executor")):
        return False
    init_methods = [
        s for s in node.body
        if isinstance(s, ast.FunctionDef) and s.name == "__init__"
    ]
    if not init_methods:
        # No explicit __init__ means default empty __init__ — counts as stateless.
        return True
    # If any __init__ overload (rare in Python, but possible via decorators) is
    # empty, treat the class as stateless.
    return any(_has_only_docstring_or_pass(m.body) for m in init_methods)


def _resolve_call_class_name(call: ast.Call) -> Optional[str]:
    """Return the constructor-call's class name when ``call.func`` is bare.

    Restricted to ``ast.Name`` to keep the rule narrow — attribute-call
    constructors (``mod.ClassName()``) are not part of the seeded baseline,
    and a direct ``ClassName()`` is what the singleton pattern uses.
    """
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _iter_singleton_assignments(
    tree: ast.Module, classes: dict
) -> List[Tuple[int, str, str]]:
    """Walk ``tree.body`` only and yield ``(lineno, class_name, target_name)``.

    Handles ``Assign`` (single ``Name`` target) and ``AnnAssign``
    (``name: T = ClassName()``). Multi-target assigns and tuple/attribute
    targets are skipped intentionally.
    """
    out: List[Tuple[int, str, str]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1:
                continue
            target = stmt.targets[0]
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target = stmt.target
            value = stmt.value
            if value is None:
                continue
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if not isinstance(value, ast.Call):
            continue
        class_name = _resolve_call_class_name(value)
        if class_name is None or class_name not in classes:
            continue
        out.append((stmt.lineno, class_name, target.id))
    return out


def _rel_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def scan() -> Tuple[List[Offense], List[Offense]]:
    """Return ``(allowlisted_hits, new_offenses)``.

    Both lists exist so the script can both confirm the seeded baseline
    matches reality and surface any new fire-able offense.
    """
    allowlisted: List[Offense] = []
    new_offenses: List[Offense] = []
    if not APP_DIR.is_dir():
        return allowlisted, new_offenses
    for path in sorted(APP_DIR.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        # Only top-level classes count as module-level singletons.
        classes = {
            s.name: s
            for s in tree.body
            if isinstance(s, ast.ClassDef) and _is_stateless_class(s)
        }
        if not classes:
            continue
        rel = _rel_path(path)
        for lineno, class_name, target_name in _iter_singleton_assignments(tree, classes):
            offense = Offense(path, lineno, class_name, target_name)
            if (rel, class_name) in ALLOWLIST:
                allowlisted.append(offense)
            else:
                new_offenses.append(offense)
    return allowlisted, new_offenses


def main() -> int:
    if not APP_DIR.is_dir():
        sys.stderr.write(f"error: {APP_DIR} not found\n")
        return 2
    allowlisted, new_offenses = scan()
    if new_offenses:
        for offense in new_offenses:
            print(offense.format())
        print(
            f"{len(new_offenses)} new stateless singleton offense(s); "
            f"{len(allowlisted)} allowlisted baseline candidate(s) detected."
        )
        return 1
    print(
        f"0 new stateless singleton offenses; "
        f"{len(allowlisted)} allowlisted baseline candidates detected."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
