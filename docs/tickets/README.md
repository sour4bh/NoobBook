# NoobBook Structure Migration Backlog

This backlog is organized as seven epics with embedded child tickets. Epic files are the human-readable source of truth. `tickets.csv` is the machine-readable index for planning views and validation scripts.

The previous flat ticket set has been archived under `docs/tickets/archive/legacy-flat/` before the new overlapping epic IDs were introduced.

Ticket bodies are the implementation source of truth. Audit files, archived tickets, and conversation history are provenance only; an assigned agent should not need them to choose ownership, target paths, or contract names.

## ID Model

| Range | Meaning |
|---|---|
| `NBB-001` through `NBB-007` | Epics |
| `NBB-101` through `NBB-109`, including `NBB-108A/B` | Foundation tasks |
| `NBB-201` through `NBB-210`, including split tasks `NBB-202A/B`, `NBB-207A/B/C`, `NBB-208A/B`, and `NBB-209A-E` | Central policy, safety, and boundary tasks |
| `NBB-301` through `NBB-304` | Chat migration tasks |
| `NBB-401` through `NBB-403` | Sources migration tasks. Permanent raw-code replacement is deferred in `D-002`. |
| `NBB-501A/B` through `NBB-507` | Studio migration tasks |
| `NBB-601` through `NBB-604` | Frontend tightening tasks |
| `NBB-701` through `NBB-706`, including split tasks `NBB-704A/B/C` and `NBB-705A-E` | Verification and cleanup tasks |

## Core Policies

- `backend/app/api` remains the transport boundary in this migration. Route files parse HTTP, run guards, call domain public surfaces, and format responses. Route movement is tracked in `DEFERRED.md`.
- New backend code should move toward domain roots rather than mechanism buckets such as `services/`, `utils/`, `ai_agents/`, `ai_services/`, `tool_executors/`, `services/tools/`, or `backend/data/prompts/`.
- Prompt JSON and tool JSON may not move until `NBB-207A` lands loader registry/shims. Prompt ownership is `NBB-207B`; tool-schema ownership is `NBB-207C`.
- `platform/files/` and `providers/files/` are not dumping grounds. Low-level external API clients and SDK wrappers belong under `providers/`; configured product capabilities belong under `connectors/`; source format operations belong under `sources/`; studio export/screenshot support belongs under `studio/`.
- `base/` and every `shared/` family require narrow charters from `NBB-104`.
- Temporary shims are allowed during migration, but `NBB-706` must remove forwarding-only modules unless a documented compatibility boundary remains.

## Implementation Responsibility

Ticket assignees should inspect the current codebase to find exact files, imports, tests, and rollout hazards, but they should not reopen the architecture decisions already captured in these tickets. If implementation reveals a contradiction or missing owner, pause the move and patch the relevant ticket, `TRACEABILITY.md`, or `DEFERRED.md` before changing product code.

Only tickets that explicitly create a decision artifact may make new placement decisions. Examples: `NBB-104` writes charters and dependency rules, `NBB-205` writes named contracts, `NBB-501A` writes the studio taxonomy, `NBB-501B` writes the studio item registry, and `NBB-503` may feed pilot findings back into `NBB-501A/501B/502` before follow-on studio migrations begin.

Tickets that move ownership should include an inline `Decision map` table. `TRACEABILITY.md` may index these maps, but it is not required implementation input.

Every task body includes `Primary write scope`. This is collision-prevention metadata for agents, not an exhaustive file inventory.

Task rows are the executable scheduling gates. Epic-row dependencies summarize the readiness gate for the full stream and may be heavier than the first task in that epic; do not use epic rows alone to decide whether a specific task can start.

## Execution Order

Foundation is not a strict serial chain after the first two tasks:

1. Run `NBB-101` first.
2. Run `NBB-102` second.
3. Then `NBB-103`, `NBB-104`, and `NBB-105` may run in parallel.
4. After `NBB-103`, `NBB-106`, `NBB-107`, and `NBB-109` may run in parallel.
5. After `NBB-105`, `NBB-108A` and `NBB-601` may run in parallel.
6. `NBB-108B` runs only if `NBB-108A` chooses baseline frontend test implementation.

Then run Epic 002 by need, not as a serialized mega-block. Downstream work unlocks by dependency slices in `tickets.csv`.

See `GRAPH.md` for execution waves generated from the machine-readable graph.

## Unlock Matrix

| Stream | May start after |
|---|---|
| Epic 003 Chat | `NBB-106`, `NBB-107`, `NBB-109`, `NBB-201`, `NBB-202A`, `NBB-205`, `NBB-206`, `NBB-207A`, `NBB-207C`, and `NBB-209A` |
| Epic 004 Sources | Skeleton/map work starts after `NBB-104` and `NBB-206`; behavior moves wait on exact task deps such as `NBB-106`, `NBB-203`, `NBB-205`, `NBB-207A/B/C`, and `NBB-202B` where applicable |
| Epic 005 Studio | Taxonomy starts after `NBB-104` and `NBB-207C`; registry and implementation work wait on exact task deps for route smokes, contracts, provider/connector boundaries, prompt/tool ownership, and background ownership |
| Epic 006 Frontend | `NBB-105` and `NBB-108A`; `NBB-108B` may run in parallel if frontend tests are chosen |
| Epic 007 Cleanup | Some split tasks, especially `NBB-704A` and `NBB-705C`, intentionally run early as owner-specific guardrails/drains; `NBB-706` is the final cleanup gate and waits for `NBB-704C` type/AST safety checks |

## Epics

| Epic | Title | File |
|---|---|---|
| `NBB-001` | Foundation and Migration Guardrails | `docs/tickets/epics/NBB-001.md` |
| `NBB-002` | Central Policy, Safety, and Shared Boundaries | `docs/tickets/epics/NBB-002.md` |
| `NBB-003` | Chat Domain Migration | `docs/tickets/epics/NBB-003.md` |
| `NBB-004` | Sources Domain Migration | `docs/tickets/epics/NBB-004.md` |
| `NBB-005` | Studio Domain Migration | `docs/tickets/epics/NBB-005.md` |
| `NBB-006` | Frontend Ownership Tightening | `docs/tickets/epics/NBB-006.md` |
| `NBB-007` | Verification, Enforcement, and Cleanup | `docs/tickets/epics/NBB-007.md` |

## Graph Generation and Validation

Regenerate `docs/tickets/GRAPH.md` from `tickets.csv`:

```bash
python3 docs/tickets/dag.py --write
```

Run CSV integrity checks (row/epic/task counts, dangling deps, anchor resolution, stale aggregate/removed-row references); exits non-zero on any issue:

```bash
python3 docs/tickets/dag.py --check
```

Combined pass for CI:

```bash
python3 docs/tickets/dag.py --check --write
```

`dag.py --check` automates the machine-checkable CSV rules. Reviewers still verify manually:

- old flat tickets are archived under `docs/tickets/archive/legacy-flat/`
- exactly seven epic files exist
- `D-002` states production raw-code analysis remains disabled until future permanent replacement
- `GRAPH.md` matches `dag.py --write` output
- no stale branch-only or old-fork clone guidance remains in new ticket docs
- no old `ai_agents/ai_services/tool_executors` taxonomy is presented as current guidance
- no audit-only deferral wording appears without an inline decision map in the same ticket
- no PR-time ownership-decision wording appears
- no unqualified `platform/files/` or `providers/files/` target appears
- no empty-`utils/` criterion appears without approved exceptions
- no unresolved studio category placeholder remains
- no `base/` or `shared/` proposal appears without a linked charter
- no prompt/tool JSON move appears before `NBB-207A`
- no permanent forwarding-only wrapper is accepted
- every task body includes `**Primary write scope:**`

See `TRACEABILITY.md` for old-ticket and finding mappings. See `DEFERRED.md` for tracked work intentionally outside this rewrite.

## Move bookkeeping

Structural movement tickets (NBB-209A–E, 304, 402, 705A–D, and partially 403, 504–507, 602–604) execute Python and TypeScript moves through the **refactory** Claude Code plugin — `mcp__refactory__move_module`, `mcp__refactory__move_symbol`, and `mcp__refactory__rename_symbol`. Refactory's `validate_imports` catches import-statement breakage after a move, but string references in docs and tests need a separate pass. `NBB-706` is verification and manual cleanup only; it does not call refactory execution tools and does not append rows to `move-plan.csv`.

`docs/tickets/move-plan.csv` is an append-only audit log of every move. Read-only metadata, not a driver script — refactory does the execution during the ticket's turn. Purpose: consolidated audit ("where did `utils/pdf_utils.py` land?") across 11+ mover tickets.

Columns (no spaces, standard CSV): `ticket,language,old_path,new_path,old_symbol,new_symbol,mode,tool`

Modes: `python_module_move`, `python_symbol_rename`, `python_symbol_move`, `json_asset_move`, `text_reference_check`.

Helpers for cases refactory does not cover (owned by `NBB-103`):

```bash
docs/tickets/helpers/json_asset_move.sh <old_path> <new_path>
   # prompt/tool JSON moves (NBB-207B/C); git mv + flags loader-registry refs

python3 docs/tickets/helpers/string_ref_scan.py <pattern>
   # grep for string module refs in docs/tests/configs
   # (monkeypatch targets, importlib strings, CLAUDE.md/AGENTS.md mentions)
```

Agent convention for every move:

1. Confirm `tool_search` surfaces `mcp__refactory__move_module`; if not, the refactory plugin is not loaded — see [`REFACTORY_SETUP.md`](REFACTORY_SETUP.md).
2. For `move_symbol` rows only: `touch` the target file before the first dry-run call.
3. Call the refactory tool with `dry_run=true`, review the diff.
4. Call the refactory tool with `dry_run=false` to apply.
5. Append one row per move to `move-plan.csv` with the ticket id.
6. Run `string_ref_scan.py <old_path>` and resolve any hits.
7. Run `pyright` on touched packages plus the NBB-106 route smokes and NBB-107 auth tests. The ticket is not done until these pass.

`.mcp.json` is gitignored; copy `.mcp.json.example` and edit the path to your local refactory checkout. Full setup (plus the `--plugin-dir` vs raw-`.mcp.json` tradeoff and dependency-hook notes) lives in [`REFACTORY_SETUP.md`](REFACTORY_SETUP.md).
