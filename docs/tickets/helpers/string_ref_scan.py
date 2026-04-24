#!/usr/bin/env python
"""
Scan the repo for string references to a module path that refactory's
validate_imports cannot see: monkeypatch targets, importlib strings,
docs/CLAUDE.md/AGENTS.md mentions, and test fixtures that name modules
as plain strings.

Usage:
  python docs/tickets/helpers/string_ref_scan.py <pattern>
  python docs/tickets/helpers/string_ref_scan.py --help

Exits 0 even when matches exist; this is informational output for a
human/agent to review before a move lands.
"""
import argparse
import re
import sys
from pathlib import Path


SCAN_ROOTS = (
    "backend",
    "frontend",
    "docs",
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "REFACTORING.md",
    "STRUCTURE.md",
)

SCAN_EXTS = (
    ".py",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".md",
    ".json",
    ".yml", ".yaml", ".toml", ".cfg", ".ini",
    ".sh",
)


def iter_files(repo_root: Path):
    for item in SCAN_ROOTS:
        path = repo_root / item
        if path.is_file():
            yield path
            continue
        if not path.is_dir():
            continue
        for sub in path.rglob("*"):
            if sub.is_file() and sub.suffix in SCAN_EXTS:
                yield sub


def scan(pattern: str, repo_root: Path) -> int:
    needle = re.compile(re.escape(pattern))
    hits = 0
    for file_path in iter_files(repo_root):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if needle.search(line):
                rel = file_path.relative_to(repo_root)
                print(f"{rel}:{lineno}: {line.strip()}")
                hits += 1
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pattern",
        nargs="?",
        default="",
        help="module path or string fragment to search for (e.g. app.utils.auth_middleware)",
    )
    args = parser.parse_args()

    if not args.pattern:
        print("no pattern given; empty scan.")
        return 0

    repo_root = Path(__file__).resolve().parents[3]
    hits = scan(args.pattern, repo_root)
    if hits == 0:
        print(f"no string references to {args.pattern!r}")
    else:
        print(f"\n{hits} matches — review each before the move lands.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
