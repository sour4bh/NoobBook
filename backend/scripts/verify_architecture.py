"""
Architecture checks for the NoobBook structure migration (NBB-704A + NBB-704B).

NBB-704A established two narrow rules that hold long before migration finishes:

1. Backend root registry. Every tracked top-level child of ``backend/app/``
   must be a canonical root from ``STRUCTURE.md`` (NBB-104/NBB-902).
   ``services`` is retired by NBB-811, and ``utils`` plus ``data/prompts`` are
   retired by NBB-812. New roots outside the approved list fail. This catches a
   contributor inventing a new mechanism bucket.

2. Import direction at the external edge (NBB-104, NBB-206).
   - ``backend/app/providers/`` is a leaf. It must not import from ``app.api``,
     ``app.connectors``, or any domain root (``app.auth``, ``app.workspaces``,
     ``app.projects``, ``app.chat``, ``app.sources``, ``app.studio``,
     ``app.brand``, ``app.background``, ``app.settings``).
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
   the public surface declared in ``app.chat.__all__`` ({store, message, tools,
   schemas, send, stream, ChatEvent, ChatResponse}). Reaching deeper paths such
   as ``app.chat.message.store`` is rejected; callers that need message
   persistence import ``message_service`` from ``app.chat.message``.

5. Inter-domain regression guard. ``app.auth/``, ``app.workspaces/``,
   ``app.projects/``, ``app.connectors/``, ``app.brand/``, ``app.background/``,
   and ``app.settings/`` currently do not import from ``app.chat``,
   ``app.sources``, or ``app.studio`` at all. Lock the property — these roots
   may not depend on the migrated domains in either direction, today or in
   future commits.

6. API transport boundary (NBB-906). Non-transport app code must not import
   ``app.api`` route modules. The app factory may register the blueprint, and
   route modules may import sibling route blueprints inside ``app.api``.

The stateless-singleton and type safety checks are owned by NBB-704C. The
sources/studio public-surface enforcement and the frontend ownership check are
intentionally deferred (see ``backend/STRUCTURE.md`` Architecture checks). This
script stays stdlib-only by design.

NBB-811 adds the services no-return rules: no current tracked file under
``backend/app/services``, no ``app.services.*`` references in backend app code
or backend tests, and no current docs that present ``services/`` as a live
destination instead of a historical migration source. NBB-812 extends the
tracked-file and import gates to ``backend/app/utils``, ``backend/data/prompts``,
``app.utils.*`` references, and current docs/deployment files that present any
retired root as live.

Usage:
    python backend/scripts/verify_architecture.py

Exits 0 when no violations are found. Exits 1 and prints one line per offense.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
REPO_ROOT = BACKEND_DIR.parent

# Canonical backend roots from STRUCTURE.md (NBB-104). Every backend file
# belongs under one of these.
CANONICAL_ROOTS: frozenset[str] = frozenset({
    "api",
    "agents",
    "auth",
    "workspaces",
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
    "config",
})

# Domain roots. Used for import-direction checks at the external edge.
DOMAIN_ROOTS: frozenset[str] = frozenset({
    "auth",
    "workspaces",
    "projects",
    "chat",
    "sources",
    "studio",
    "brand",
    "background",
    "settings",
})

TOLERATED_ROOTS: frozenset[str] = frozenset()

RETIRED_PATHS: Tuple[Tuple[str, str], ...] = (
    (
        "backend/app/services",
        "backend/app/services is retired by NBB-811. Move this file to an "
        "owning canonical root; no app.services compatibility shim is allowed.",
    ),
    (
        "backend/app/utils",
        "backend/app/utils is retired by NBB-812. Move this file to an owning "
        "canonical root; no app.utils compatibility shim is allowed.",
    ),
    (
        "backend/data/prompts",
        "backend/data/prompts is retired by NBB-812. Move this prompt asset to "
        "an owning registered prompt directory.",
    ),
)

RETIRED_IMPORTS: Tuple[Tuple[str, str], ...] = (
    (
        "app.services.",
        "app.services imports are forbidden after NBB-811. Import from the "
        "owning canonical root instead.",
    ),
    (
        "app.utils.",
        "app.utils imports are forbidden after NBB-812. Import from app.base "
        "or the owning domain root instead.",
    ),
)

# providers/ is a leaf; it must not depend on api, connectors, or any domain.
PROVIDERS_FORBIDDEN_PREFIXES: Tuple[str, ...] = tuple(
    sorted({"api", "connectors"} | set(DOMAIN_ROOTS))
)

# connectors/ may depend on providers, auth, workspaces, and projects
# (per CHARTER.md). Workspace-scoped connector settings are product-owned
# capability state rather than raw provider SDK behavior.
# Anything else under app. is a boundary violation.
CONNECTORS_ALLOWED_PREFIXES: frozenset[str] = frozenset({
    "providers",
    "auth",
    "workspaces",
    "projects",
})
CONNECTORS_FORBIDDEN_PREFIXES: Tuple[str, ...] = tuple(
    sorted(
        ({"api"} | set(DOMAIN_ROOTS)) - CONNECTORS_ALLOWED_PREFIXES
    )
)

# NBB-704B path (a): inherited providers→domain imports that landed with
# NBB-705C. Each entry is ``(rel_path, lineno, target_root)`` so a future
# re-fire on a different line still surfaces. Rationale lives in
# ``providers/CHARTER.md`` "Documented exceptions (NBB-704B)".
INHERITED_PROVIDER_VIOLATIONS: frozenset[Tuple[str, int, str]] = frozenset({
    ("backend/app/providers/anthropic/token_count.py", 12, "sources"),
})

# NBB-807 moved Freshdesk sync into connectors without changing source
# processing behavior. These two lazy imports are inherited progress and
# cancellation hooks used by the existing source-processing callers; changing
# that callback contract belongs with the source-processing move, not this
# connector relocation.
INHERITED_CONNECTOR_VIOLATIONS: frozenset[Tuple[str, int, str]] = frozenset({
    ("backend/app/connectors/freshdesk/sync.py", 52, "background"),
    ("backend/app/connectors/freshdesk/sync.py", 74, "sources"),
})

# NBB-704B rule 4: chat public surface, derived from ``app.chat.__all__``.
# A non-chat caller must reach chat via these submodules; any deeper path
# (``app.chat.message.store``, ``app.chat.loop``, ``app.chat.tool.policy``,
# etc.) is a boundary violation.
CHAT_PUBLIC_SUBMODULES: frozenset[str] = frozenset({
    "message",
    "store",
    "tools",
    "schemas",
})

# NBB-704B rule 5: roots that currently have zero cross-domain imports into
# ``app.chat``, ``app.sources``, or ``app.studio``. Lock that property as a
# regression guard — these roots stay independent of the migrated domains.
INDEPENDENT_ROOTS: Tuple[str, ...] = (
    "auth",
    "workspaces",
    "projects",
    "connectors",
    "brand",
    "background",
    "settings",
)
MIGRATED_DOMAINS: Tuple[str, ...] = ("chat", "sources", "studio")

INDEPENDENT_ROOTS_ALLOWLIST: frozenset[Tuple[str, int, str]] = frozenset({
    ("backend/app/connectors/freshdesk/sync.py", 74, "sources"),
})

AI_DOMAIN_FORBIDDEN_TOKENS: Tuple[Tuple[str, str], ...] = (
    (
        "claude_service.send_message",
        "domain code must not call claude_service.send_message directly after "
        "NBB-1111. Use app.agents.runtime or the provider adapter boundary.",
    ),
    (
        "claude_service.stream_message",
        "domain code must not call claude_service.stream_message directly after "
        "NBB-1111. Use app.agents.runtime or the provider adapter boundary.",
    ),
    (
        "tool_loader.load_tool(",
        "domain code must not request Anthropic-shaped tool dictionaries after "
        "NBB-1111. Load ToolSpec contracts and compile them through the runtime "
        "provider boundary.",
    ),
    (
        "tool_loader.load_tools_for_agent(",
        "domain code must not request Anthropic-shaped agent tool dictionaries "
        "after NBB-1111. Load ToolSpec contracts and compile them through the "
        "runtime provider boundary.",
    ),
    (
        "tool_loader.load_tools_from_category(",
        "domain code must not request provider-shaped tool dictionaries after "
        "NBB-1111. Load ToolSpec contracts and compile them through the "
        "runtime provider boundary.",
    ),
)

AI_FORBIDDEN_ANTHROPIC_INTERNAL_IMPORTS: Tuple[str, ...] = (
    "app.providers.anthropic.response_parser",
    "app.providers.anthropic.content",
)

TOOL_BINDING_ALLOWLIST: Set[str] = {
    # Chat memory has one internal forced tool; its executable binding is
    # colocated with the memory update workflow while specs remain catalog-owned.
    "backend/app/chat/memory/tools",
    # These single terminating tools only echo validated input. Their handlers
    # stay at the call site so we do not create binding.py files that repeat
    # what the spec and runtime binding call already say.
    "backend/app/sources/pdf/tools",
    "backend/app/sources/pptx/tools",
    "backend/app/sources/image/tools",
    "backend/app/studio/design/flow_diagram/tools",
    "backend/app/studio/learning/flash_card/tools",
    "backend/app/studio/learning/mind_map/tools",
    "backend/app/studio/learning/quiz/tools",
    "backend/app/connectors/jira/tools",
    "backend/app/connectors/mixpanel/tools",
    "backend/app/connectors/notion/tools",
}

CURRENT_DOC_PATHS: Tuple[Path, ...] = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "STRUCTURE.md",
    BACKEND_DIR / "STRUCTURE.md",
    BACKEND_DIR / "Dockerfile",
    BACKEND_DIR / "entrypoint.sh",
    REPO_ROOT / "docs/deployment/observability.md",
    REPO_ROOT / "docs/contracts/README.md",
)

RETIRED_DOC_TARGETS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    (
        "services/",
        (
            "backend/app/services",
            "app/services",
            "services/",
            "app.services.",
        ),
        "NBB-811",
    ),
    (
        "utils/",
        (
            "backend/app/utils",
            "app/utils",
            "app.utils.",
            "utils/text/",
            "utils/logger",
            "utils/path_utils",
            "utils/claude_parsing_utils",
            "utils/cost_tracking",
            "utils/embedding_utils",
            "utils/file_utils",
            "utils/citation_utils",
            "utils/source_content_utils",
            "utils/pdf_utils",
            "utils/pptx_utils",
            "utils/docx_utils",
            "utils/rate_limit_utils",
            "utils/encoding_utils",
            "utils/presentation_export_utils",
            "utils/screenshot_utils",
            "utils/excalidraw_utils",
            "utils/password_utils",
            "utils/auth_middleware",
        ),
        "NBB-812",
    ),
    (
        "data/prompts/",
        (
            "backend/data/prompts",
            "data/prompts/",
            "data/prompts",
        ),
        "NBB-812",
    ),
)

ACTIVE_RETIRED_GUIDANCE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(new|add|create|place|put|land|lives?|belongs?|destination|owner|"
        r"backend owner|may read|may import|tolerated|current|currently|"
        r"remains|feed|feeds|use|uses|using|under|seed|seeds|sync|copy|cp|"
        r"stage|staging|baked|volume|mkdir|ensure|write|writes)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(new|add|create|place|put|land|lives?|belongs?|destination|owner|"
        r"backend owner|may read|may import|tolerated|current|currently|"
        r"remains|feed|feeds|use|uses|using|under|seed|seeds|sync|copy|cp|"
        r"stage|staging|baked|volume|mkdir|ensure|write|writes)",
        re.IGNORECASE,
    ),
)

RETIRED_NO_RETURN_MARKERS: Tuple[str, ...] = (
    "not approved",
    "frozen",
    "do not add",
    "do not recreate",
    "must remain empty",
    "must not",
    "forbidden",
    "fail",
    "no-return",
    "no return",
    "reject",
    "retired",
    "legacy",
    "replaces",
    "rather than",
    "former",
    "formerly",
    "migrated",
    "migration source",
    "moved",
    "moves",
    "removed",
    "drained",
    "deleted",
    "historical",
)

RETIRED_LIVE_MARKERS: Tuple[str, ...] = (
    "tolerated",
    "still contain",
    "remains",
    "feed this root",
    "feeds this root",
    "may read",
    "may import",
    "backend owner",
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
    approved = CANONICAL_ROOTS | TOLERATED_ROOTS
    violations: List[Violation] = []
    tracked_files, error = _git_ls_files("backend/app")
    if error is not None:
        return [Violation(None, 0, error)]
    root_names: set[str] = set()
    for rel_path in tracked_files:
        path = REPO_ROOT / rel_path
        if not path.exists():
            continue
        parts = Path(rel_path).parts
        if len(parts) < 3:
            continue
        name = parts[2]
        if name.startswith((".", "_")):
            continue
        if len(parts) == 3:
            if name == "__init__.py":
                continue
            suffix = Path(name).suffix
            if suffix and suffix != ".py":
                continue
            name = Path(name).stem
        root_names.add(name)

    for name in sorted(root_names):
        if name in approved:
            continue
        path = APP_DIR / name
        kind = "module" if path.with_suffix(".py").is_file() else "package"
        violations.append(Violation(
            path,
            0,
            (
                f"new backend root {kind} '{name}' is not in the canonical "
                "root list from STRUCTURE.md (NBB-104). Add the file under an "
                "approved domain root instead."
            ),
        ))
    return violations


def _git_ls_files(*pathspecs: str) -> Tuple[List[str], Optional[str]]:
    cmd = ["git", "ls-files", *pathspecs]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        return [], f"{' '.join(cmd)} failed: {stderr}"
    return [line for line in result.stdout.splitlines() if line], None


def check_no_retired_paths() -> List[Violation]:
    """NBB-811/NBB-812: retired roots cannot contain tracked files."""
    violations: List[Violation] = []
    for pathspec, message in RETIRED_PATHS:
        tracked_files, error = _git_ls_files(pathspec)
        if error is not None:
            violations.append(Violation(None, 0, error))
            continue
        for rel_path in tracked_files:
            violations.append(Violation(REPO_ROOT / rel_path, 0, message))
    return violations


def check_no_retired_imports() -> List[Violation]:
    """NBB-811/NBB-812: retired app imports may not return."""
    violations: List[Violation] = []
    roots = (APP_DIR, BACKEND_DIR / "tests")
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                violations.append(Violation(path, 0, f"cannot read file: {exc}"))
                continue
            for index, line in enumerate(lines, start=1):
                for token, message in RETIRED_IMPORTS:
                    if token not in line:
                        continue
                    violations.append(Violation(path, index, message))
    return violations


def _iter_current_doc_paths() -> Iterable[Path]:
    yield from CURRENT_DOC_PATHS
    for path in sorted(APP_DIR.glob("*/CHARTER.md")):
        yield path
    for path in sorted(APP_DIR.glob("*/__init__.py")):
        yield path
    for path in sorted(APP_DIR.glob("*/README.md")):
        yield path


def _is_allowed_retired_history(line: str) -> bool:
    lower = line.lower()
    if not any(marker in lower for marker in RETIRED_NO_RETURN_MARKERS):
        return False
    return not any(marker in lower for marker in RETIRED_LIVE_MARKERS)


def check_no_live_retired_root_docs() -> List[Violation]:
    """NBB-811/NBB-812: current guidance must not present retired roots as live."""
    violations: List[Violation] = []
    seen: set[Path] = set()
    for path in _iter_current_doc_paths():
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(Violation(path, 0, f"cannot read file: {exc}"))
            continue
        for index, line in enumerate(lines, start=1):
            for label, tokens, ticket in RETIRED_DOC_TARGETS:
                if not any(token in line for token in tokens):
                    continue
                if _is_allowed_retired_history(line):
                    continue
                if not any(
                    pattern.search(line)
                    for pattern in ACTIVE_RETIRED_GUIDANCE_PATTERNS
                ):
                    continue
                violations.append(Violation(
                    path,
                    index,
                    (
                        f"current docs must not describe {label} as a live "
                        f"destination after {ticket}; keep only no-return or "
                        "historical migration wording."
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
        allowlist=INHERITED_CONNECTOR_VIOLATIONS,
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
                    "app.chat.message / app.chat.tools / app.chat.schemas) "
                    "per chat/__init__.py and chat/CHARTER.md (NBB-704B)."
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


def check_no_external_api_imports() -> List[Violation]:
    """NBB-906: app code outside the transport layer may not import routes."""
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if _is_under(path, "api"):
            continue
        if path == APP_DIR / "__init__.py":
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
            if module == "app.api" or module.startswith("app.api."):
                violations.append(Violation(
                    path,
                    lineno,
                    (
                        "non-transport app code must not import app.api route "
                        "modules. Route modules are HTTP adapters only; call "
                        "the owning domain surface instead (NBB-906)."
                    ),
                ))
    return violations


def check_no_legacy_ai_domain_access() -> List[Violation]:
    """NBB-1111: domains must not bypass the typed model/tool runtime."""
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = _rel_path(path)
        if rel.startswith("backend/app/providers/"):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(Violation(path, 0, f"cannot read file: {exc}"))
            continue

        for index, line in enumerate(lines, start=1):
            for token, message in AI_DOMAIN_FORBIDDEN_TOKENS:
                if token in line:
                    violations.append(Violation(path, index, message))

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            violations.append(Violation(path, exc.lineno or 0, f"syntax error: {exc.msg}"))
            continue
        for lineno, module in _iter_import_modules(tree):
            if module in AI_FORBIDDEN_ANTHROPIC_INTERNAL_IMPORTS:
                violations.append(Violation(
                    path,
                    lineno,
                    (
                        f"domain code must not import '{module}' after "
                        "NBB-1111. Use app.providers.anthropic.adapter or "
                        "app.agents.runtime contracts instead."
                    ),
                ))

    return violations


def check_no_static_tool_json() -> List[Violation]:
    """NBB-1111: tool schemas are Pydantic ToolSpec contracts, not JSON files."""
    tracked_files, error = _git_ls_files("backend/app")
    if error is not None:
        return [Violation(None, 0, error)]

    violations: List[Violation] = []
    for rel_path in tracked_files:
        path = Path(rel_path)
        absolute_path = REPO_ROOT / rel_path
        if not absolute_path.exists():
            continue
        if path.suffix != ".json":
            continue
        if "tools" not in path.parts and "raw_tools" not in path.parts:
            continue
        violations.append(Violation(
            absolute_path,
            0,
            (
                "static tool JSON is forbidden after NBB-1111. Define the "
                "tool in the owning domain's tools/specs.py as a ToolSpec."
            ),
        ))
    return violations


def check_no_static_prompt_json() -> List[Violation]:
    """NBB-1113: built-in prompts are Python PromptSpec contracts."""
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*_prompt.json")):
        violations.append(Violation(
            path,
            0,
            (
                "built-in prompt JSON is forbidden after NBB-1113. Define the "
                "prompt in the owning domain's prompt.py as a PromptSpec."
            ),
        ))
    return violations


def check_prompt_modules_export_specs() -> List[Violation]:
    """NBB-1113: prompt.py modules must be discoverable typed specs."""
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("prompt.py")):
        if path == APP_DIR / "config" / "prompt.py":
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
        exported = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        if "PROMPT" in exported or "PROMPTS" in exported:
            continue
        violations.append(Violation(
            path,
            0,
            (
                "prompt.py modules are prompt-spec modules after NBB-1113. "
                "Export PROMPT or PROMPTS with PromptSpec values, or rename "
                "non-prompt behavior to its real local concept."
            ),
        ))
    return violations


def check_no_obsolete_prompt_asset_apis() -> List[Violation]:
    """NBB-1113: prompt JSON path registry APIs must not return."""
    forbidden = (
        "register_prompt_path",
        "resolve_prompt_path",
        "iter_registered_prompt_dirs",
        "iter_prompt_candidate_paths",
        "_PRODUCTION_PROMPT_PATHS",
    )
    violations: List[Violation] = []
    for path in sorted((APP_DIR / "config").rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(Violation(path, 0, f"cannot read file: {exc}"))
            continue
        for index, line in enumerate(lines, start=1):
            for token in forbidden:
                if token in line:
                    violations.append(Violation(
                        path,
                        index,
                        (
                            f"obsolete prompt asset API {token!r} is forbidden "
                            "after NBB-1113. Built-in prompts are discovered "
                            "from domain prompt.py modules."
                        ),
                    ))
    return violations


def check_no_domain_prompt_config_dict_reads() -> List[Violation]:
    """NBB-1113: domain model callers render typed prompts, not config dicts."""
    forbidden = (
        "prompt_loader.get_prompt_config(",
        "prompt_loader.get_project_prompt_config(",
        "from app.config.prompt import prompt_loader",
    )
    allowed_prefixes = (
        "backend/app/api/prompts/",
        "backend/app/config/prompt.py",
    )
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = _rel_path(path)
        if rel.startswith(allowed_prefixes):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            violations.append(Violation(path, 0, f"cannot read file: {exc}"))
            continue
        for index, line in enumerate(lines, start=1):
            for token in forbidden:
                if token in line:
                    violations.append(Violation(
                        path,
                        index,
                        (
                            "domain model callers must use render_prompt after "
                            "NBB-1113. prompt_loader remains only for the public "
                            "prompt API and persisted project-prompt compatibility."
                        ),
                    ))
    return violations


def _call_local_name(node: ast.Call) -> Optional[str]:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def check_no_native_tool_loop_calls() -> List[Violation]:
    """NBB-011: runtime owns model calls and tool loops."""
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = _rel_path(path)
        if rel.startswith("backend/app/agents/runtime/"):
            continue
        if rel.startswith("backend/app/providers/"):
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

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_local_name(node)
            if name == "runtime_parts_to_native_content":
                violations.append(Violation(
                    path,
                    node.lineno,
                    (
                        "domain code must not reconstruct provider-native "
                        "content from runtime parts. Persist or pass "
                        "RunMessage/ContentPart contracts instead."
                    ),
                ))
                continue
            if name not in {"run_native_turn", "stream_native_turn"}:
                continue
            violations.append(Violation(
                path,
                node.lineno,
                (
                    "run_native_turn/stream_native_turn are forbidden after "
                    "NBB-011. Build a RunRequest and call run_with_provider "
                    "or stream_with_provider."
                ),
            ))
    return violations


def check_no_domain_tool_call_payload_reads() -> List[Violation]:
    """NBB-011: domains consume validated tool results, not provider tool calls."""
    violations: List[Violation] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = _rel_path(path)
        if rel.startswith("backend/app/agents/runtime/"):
            continue
        if rel.startswith("backend/app/providers/"):
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

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr != "tool_calls":
                continue
            violations.append(Violation(
                path,
                node.lineno,
                (
                    "domain code must consume validated RunResult.tool_results "
                    "instead of provider/model tool_calls. Use the runtime result "
                    "helper for business payloads."
                ),
            ))
    return violations


def check_tool_specs_have_bindings() -> List[Violation]:
    """NBB-011: executable local tool contracts need sibling binding modules."""
    violations: List[Violation] = []
    for specs_path in sorted(APP_DIR.rglob("specs.py")):
        rel_parent = _rel_path(specs_path.parent)
        if not (rel_parent.endswith("/tools") or rel_parent.endswith("/raw_tools")):
            continue
        if rel_parent in TOOL_BINDING_ALLOWLIST:
            continue
        binding_path = specs_path.with_name("binding.py")
        if binding_path.exists():
            continue
        violations.append(Violation(
            specs_path,
            0,
            (
                "tool specs must have a sibling binding.py so static Pydantic "
                "contracts and executable per-run handlers stay paired."
            ),
        ))
    return violations


def check_no_trivial_echo_binding_modules() -> List[Violation]:
    """NBB-1112: echo-only terminating tools stay bound at call sites."""
    violations: List[Violation] = []
    for rel_parent in sorted(TOOL_BINDING_ALLOWLIST):
        if rel_parent not in {
            "backend/app/sources/pdf/tools",
            "backend/app/sources/pptx/tools",
            "backend/app/sources/image/tools",
            "backend/app/studio/design/flow_diagram/tools",
            "backend/app/studio/learning/flash_card/tools",
            "backend/app/studio/learning/mind_map/tools",
            "backend/app/studio/learning/quiz/tools",
        }:
            continue
        binding_path = REPO_ROOT / rel_parent / "binding.py"
        if not binding_path.exists():
            continue
        violations.append(Violation(
            binding_path,
            0,
            (
                "this single-tool echo binding is intentionally inline after "
                "NBB-1112. Delete binding.py and bind echo_input at the owning "
                "workflow call site."
            ),
        ))
    return violations


def main() -> int:
    if not APP_DIR.is_dir():
        sys.stderr.write(f"error: {APP_DIR} not found\n")
        return 2

    violations: List[Violation] = []
    violations.extend(check_root_registry())
    violations.extend(check_no_retired_paths())
    violations.extend(check_no_retired_imports())
    violations.extend(check_no_live_retired_root_docs())
    violations.extend(check_providers_imports())
    violations.extend(check_connectors_imports())
    violations.extend(check_chat_publics_only())
    violations.extend(check_independent_roots())
    violations.extend(check_no_external_api_imports())
    violations.extend(check_no_legacy_ai_domain_access())
    violations.extend(check_no_static_tool_json())
    violations.extend(check_no_static_prompt_json())
    violations.extend(check_prompt_modules_export_specs())
    violations.extend(check_no_obsolete_prompt_asset_apis())
    violations.extend(check_no_domain_prompt_config_dict_reads())
    violations.extend(check_no_native_tool_loop_calls())
    violations.extend(check_no_domain_tool_call_payload_reads())
    violations.extend(check_tool_specs_have_bindings())
    violations.extend(check_no_trivial_echo_binding_modules())

    if violations:
        for v in violations:
            print(v.format())
        print(f"{len(violations)} architecture violation(s)")
        return 1

    print("0 architecture violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
