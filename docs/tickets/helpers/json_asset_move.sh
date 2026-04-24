#!/usr/bin/env bash
# docs/tickets/helpers/json_asset_move.sh
#
# Move a JSON asset (prompt or tool schema) and surface loader-registry
# references that name the old path. Refactory does not handle JSON assets;
# this helper fills the gap for NBB-207B (prompt JSON) and NBB-207C (tool JSON).
#
# Default is dry-run (matching the refactory agent convention in NBB-103);
# mutation requires explicit --apply. Never mutates without --apply.
#
# Dry-run behavior:
#   1. Report the planned `git mv <old_path> <new_path>`.
#   2. Grep backend/ and docs/ for the old path; print matches that will need
#      manual updates after the move lands.
#   3. Touch no files.
#
# --apply behavior:
#   1. `git mv <old_path> <new_path>`.
#   2. Print the same string-reference report so the human/agent can update
#      loader-registry entries.

set -euo pipefail

usage() {
    cat <<'EOF'
json_asset_move.sh — move a JSON asset and flag loader-registry references.

Usage:
  json_asset_move.sh <old_path> <new_path>             # dry-run (default)
  json_asset_move.sh <old_path> <new_path> --apply     # execute the move
  json_asset_move.sh --help

Arguments:
  old_path   path to the JSON asset, relative to repo root
  new_path   target path, relative to repo root

Owning tickets: NBB-207B (prompt JSON), NBB-207C (tool JSON).

After --apply, update any flagged loader-registry entries and append a row
to docs/tickets/move-plan.csv with mode=json_asset_move, tool=json_asset_move.sh.
EOF
}

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

if [[ $# -lt 2 ]]; then
    echo "error: need <old_path> <new_path>" >&2
    usage >&2
    exit 2
fi

old_path="$1"
new_path="$2"
mode="dry-run"

if [[ "${3:-}" == "--apply" ]]; then
    mode="apply"
elif [[ $# -ge 3 ]]; then
    echo "error: unknown flag ${3}; only --apply is supported" >&2
    exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ ! -f "$old_path" ]]; then
    echo "error: source does not exist: $old_path" >&2
    exit 1
fi

echo "mode: $mode"
echo "planned move: $old_path -> $new_path"
echo

echo "string references that will need manual update:"
grep -rn --include='*.py' --include='*.json' --include='*.md' \
    -e "$old_path" backend/ docs/ 2>/dev/null || echo "  (none found)"

if [[ "$mode" == "dry-run" ]]; then
    echo
    echo "dry-run only — re-run with --apply to execute."
    exit 0
fi

mkdir -p "$(dirname "$new_path")"
git mv "$old_path" "$new_path"
echo
echo "moved: $old_path -> $new_path"
echo "remember: append a row to docs/tickets/move-plan.csv with mode=json_asset_move"
