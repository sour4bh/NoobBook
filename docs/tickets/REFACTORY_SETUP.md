# Refactory Setup

This doc is agent-targeted setup for the `docs/tickets/` migration program. It documents how to enable the **refactory** Claude Code plugin so movement tickets share one codemod backend, plus the safety rules agents must follow.

Refactory exposes four MCP tools — `move_module`, `move_symbol`, `rename_symbol`, `validate_imports` — backed by rope (Python) and ts-morph (TypeScript). NBB-103 wires it into NoobBook; movement tickets call refactory tools directly. The safety contract is refactory dry-run, apply, `validate_imports`, string-reference scan, pyright on touched packages, and the relevant ticket tests.

## When you need this

You need refactory enabled in your session if your current ticket is one of:

- `NBB-201` (mechanical rows only), `NBB-209A`–`NBB-209E`
- `NBB-304`, `NBB-402`, `NBB-403`
- `NBB-504`, `NBB-505`, `NBB-506`, `NBB-507`
- `NBB-602`, `NBB-603`, `NBB-604`
- `NBB-705A`, `NBB-705B`, `NBB-705C`, `NBB-705D`

You do **not** need refactory for `NBB-109`, `NBB-207B`, or `NBB-207C` (those use direct edits or `docs/tickets/helpers/json_asset_move.sh`), nor for `NBB-706` (verification and manual cleanup — may still call refactory's `validate_imports` if the plugin is loaded, but does not execute moves or renames).

## Setup

1. Clone refactory wherever convenient (e.g. `~/dev/refactory`).
2. **Recommended — use the plugin loader.** Start Claude Code with refactory enabled as a plugin:
   ```bash
   claude --plugin-dir /path/to/refactory
   ```
   This triggers refactory's `SessionStart` hook, which auto-installs `rope`, `mcp`, and `ts-morph` on first run. No extra work for Python or TypeScript coverage.
3. **Fallback — raw MCP registration.** If you must use `.mcp.json` instead (e.g. starting Claude without `--plugin-dir`):
   ```bash
   cp .mcp.json.example .mcp.json
   # Edit .mcp.json: replace <PATH_TO_REFACTORY> with the absolute path
   ```
   The `.mcp.json` path starts refactory's `server/main.py` directly and **skips the `SessionStart` hook**, so install dependencies manually first:
   ```bash
   pip install rope mcp
   (cd /path/to/refactory/server/tsmorph && pnpm install)
   ```
   Skip the `pnpm install` only if you won't touch TypeScript (e.g. backend-only tickets).

   `.mcp.json` is gitignored — paths are per-contributor, never committed.

## Self-check before editing code

In any agent session, confirm `tool_search` surfaces refactory's `move_module` tool. It appears as one of two namespaces depending on how refactory loaded:

- `mcp__refactory__move_module` — raw `.mcp.json` registration.
- `mcp__plugin_refactory_refactory__move_module` — `--plugin-dir` plugin-framework load (the recommended path).

Either namespace is fine — the agent specs allowlist both. If neither surfaces, the plugin is not loaded — **stop and fix session setup before editing code**. Silent fallback to manual import editing is a failure mode the migration is designed to avoid.

## Safety rules

- **Dry-run first.** Refactory's MCP schema defaults `dry_run` to `false`, so the dry-run discipline is agent policy, not tool-enforced. Call every tool with `dry_run=true`, review the diff, then call again with `dry_run=false` to apply.
- **`move_symbol` needs the target file to exist.** Refactory's Python `move_symbol` dry-run fails if the target module is not on disk. `touch backend/app/<new_path>` before the first dry-run.
- **Append to `move-plan.csv` after every move.** One row per operation, ticket id in the first column.
- **Run `string_ref_scan.py` for the old path.** Refactory's `validate_imports` only sees import statements — string references (monkeypatch targets, `importlib` strings, doc mentions) need a separate pass.
- **`validate_imports` stdlib noise.** Rope cannot resolve Python stdlib names (`datetime`, `decimal`, `concurrent.futures`, etc.) against NoobBook's `backend/` without venv wiring. Running `validate_imports` at `project_root=backend/` returns a baseline of 100+ false-positive `unresolved_import_name` errors on current `main`. Scope each run narrowly to the moved files (pass a `project_root` pointing at the moved package when possible), compare the error set against the pre-move baseline, and treat only *new* errors as merge-blocking. Record the delta in the worker's `NOTES`.
- **Post-apply checks.** Run `pyright` on touched packages plus the `NBB-106` route smokes and `NBB-107` auth tests. The ticket is not done until these pass.

## JSON assets (NBB-207B/C)

Refactory does not move JSON files. Use `docs/tickets/helpers/json_asset_move.sh` instead. Default mode is dry-run; mutation requires `--apply`.

```bash
docs/tickets/helpers/json_asset_move.sh <old> <new>             # dry-run
docs/tickets/helpers/json_asset_move.sh <old> <new> --apply     # execute
```

## Further reading

- `docs/tickets/README.md` → "Move bookkeeping" — end-to-end workflow and `move-plan.csv` schema.
- `NBB-103` ticket body — full scope and acceptance criteria.
