"""
Fail when a new file is added under a frozen legacy destination.

Frozen destinations are the migration sources named in `STRUCTURE.md` and the
`NBB-103` ticket body. Some prefixes are now fully retired no-return roots. New
files must not land there unless an explicit allowlist row names them.

Usage:
    python scripts/ci/check_no_new_legacy_files.py --base origin/main

The script inspects the set of added files (`git diff --name-status
--diff-filter=A <base>...HEAD`). Any path under a frozen prefix that is not in
`scripts/ci/no_new_legacy_files_allowlist.txt` fails the check.
"""
import argparse
import subprocess
import sys
from pathlib import Path


FROZEN_PREFIXES: tuple[str, ...] = (
    "backend/app/services/ai_agents/",
    "backend/app/services/ai_services/",
    "backend/app/services/tool_executors/",
    "backend/app/services/tools/",
    "backend/app/services/studio_services/jobs/",
    "backend/app/services/studio_services/studio_processing/",
    "backend/app/services/",
    "backend/app/utils/",
    "backend/data/prompts/",
    "frontend/src/components/hooks/",
)

SCRIPT_DIR = Path(__file__).resolve().parent
ALLOWLIST_PATH = SCRIPT_DIR / "no_new_legacy_files_allowlist.txt"


def load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    entries: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def added_files(base_ref: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=A", f"{base_ref}...HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"check_no_new_legacy_files: git diff against '{base_ref}' failed:\n"
            f"{exc.stderr}"
        )
        raise SystemExit(2)
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts
        if status.startswith("A"):
            paths.append(path)
    return paths


def matching_prefix(path: str) -> str | None:
    for prefix in FROZEN_PREFIXES:
        if path.startswith(prefix):
            return prefix
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref to diff against (default: origin/main).",
    )
    parser.add_argument(
        "--allowlist",
        default=str(ALLOWLIST_PATH),
        help="Allowlist file path (default: co-located allowlist).",
    )
    args = parser.parse_args()

    allowlist = load_allowlist(Path(args.allowlist))
    violations: list[tuple[str, str]] = []
    for path in added_files(args.base):
        prefix = matching_prefix(path)
        if prefix is None:
            continue
        if path in allowlist:
            continue
        violations.append((path, prefix))

    if not violations:
        return 0

    sys.stderr.write(
        "check_no_new_legacy_files: new files under frozen destinations "
        "require an allowlist entry with a reviewer-approved reason.\n"
    )
    for path, prefix in violations:
        sys.stderr.write(f"  {path}  (frozen prefix: {prefix})\n")
    sys.stderr.write(
        f"Allowlist file: {args.allowlist}\n"
        "Add the path on its own line (comments via '#') if reviewers approve.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
