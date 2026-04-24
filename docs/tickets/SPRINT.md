# NoobBook Migration Sprint Control

This file is the durable sprint control artifact for executing the structure migration. It does not replace ticket bodies, `tickets.csv`, `GRAPH.md`, `TRACEABILITY.md`, or `DEFERRED.md`.

## Source of Truth

| Artifact | Role |
|---|---|
| `docs/tickets/tickets.csv` | Machine-readable task list and hard dependency graph. |
| `docs/tickets/GRAPH.md` | Generated execution waves and dependency diagrams. |
| `docs/tickets/epics/*.md` | Human-readable ticket scope, decisions, write scopes, and acceptance criteria. |
| `docs/tickets/DEFERRED.md` | Explicitly deferred work and safety guardrails. |
| `docs/tickets/move-plan.csv` | Append-only audit log for mechanical moves. |
| `docs/tickets/SPRINT.md` | Operational plan, current wave, assignment, merge, and verification discipline. |

Hard gates live in `tickets.csv`. Ticket bodies carry implementation detail. This file coordinates execution only.

## Current Baseline

As of sprint start:

- Branch: `develop`
- Graph shape: 66 CSV rows, 7 epics, 59 tasks
- Graph validation: `python docs/tickets/dag.py --check`
- Refactory plugin: required for movement tickets; verify each session with `tool_search` for `mcp__refactory__move_module`
- Permanent raw-code analysis replacement: out of scope, tracked by `D-002`
- Route movement out of `backend/app/api`: out of scope, tracked by `D-001`

## Execution Rules

1. A task may start only when every task in its `depends_on` field has merged to `develop`.
2. Epic-row dependencies are not scheduling gates for individual tasks.
3. If implementation reveals a missing owner or contradiction, pause product-code edits and patch the owning ticket or deferred register first.
4. No movement ticket may bypass refactory unless the ticket explicitly says the change is manual.
5. Refactory calls are dry-run first, apply second.
6. Every mechanical move appends one row to `docs/tickets/move-plan.csv`.
7. Forwarding shims are temporary and must be removed or justified by `NBB-706`.
8. Agents must not revert unrelated edits from other agents.

## Roles and Authority

All irreversible repo state changes — `git merge`, `git push`, branch deletion, worktree removal — are the top-level dispatcher's responsibility only.

Claude subagents (`nbb-lead`, `nbb-worker`, `nbb-reviewer`) plan, implement, review, and update `SPRINT.md`. They do not merge, push, delete branches, or remove worktrees.

Invariant:

```text
Claude agents plan, implement, review, and update SPRINT.md.
Top-level dispatcher merges, pushes, and removes worktrees.
```

This keeps all destructive or history-altering operations in one place.

## Lead Integrator Duties

The lead integrator is the top-level dispatcher and owns sprint flow, not ticket implementation. All irreversible repo state changes are the integrator's alone.

- Keep `develop` green.
- Merge dependency-gate tickets before dependent tickets (subagents cannot merge).
- Remove worker and reviewer worktrees after merge (`git worktree remove`) and prune stale metadata (`git worktree prune`).
- Run `python docs/tickets/dag.py --check` after ticket graph edits.
- Review `move-plan.csv` for one row per mechanical operation.
- Verify each worker and reviewer result reports files touched, tests run, and any skipped checks.
- Resolve merge conflicts and decide whether a contradiction requires a ticket patch.
- Keep this file's status tables current (may delegate `SPRINT.md` updates to `nbb-lead`).

## Durable State Protocol

`SPRINT.md` is the resume point for the lead dispatcher. After every worker result, reviewer result, merge, blocker, or skipped ticket, update only the compact state needed to continue the sprint.

Cross-system communication rule: Codex and Claude-side agents communicate sprint state only through this file. Chat history, hidden subagent context, raw transcripts, local scratch notes, and sidecar planning files are not operational state.

Do record:

- ticket status and current owner;
- worker branch or worktree path;
- reviewer recommendation;
- merge commit when merged;
- required checks and whether they passed, failed, or were skipped;
- blocker owner and the next decision needed.

Do not record:

- raw worker transcripts;
- raw reviewer transcripts;
- long diffs;
- speculative architecture notes;
- ticket-scope changes that belong in `docs/tickets/epics/*.md`.

Resume rule: a new lead session reads this file, `tickets.csv`, and `GRAPH.md`, then recomputes the ready set. Chat history is advisory only; durable state in this file wins.

## Control Plane Handoff

Use this table for short operational messages between Codex, Claude lead, workers, reviewers, and the human operator. Keep entries action-oriented and mark them resolved only when their state has moved into the sprint board, blocker log, decision log, or git history.

| Date | From | To | Topic | Message | Status |
|---|---|---|---|---|---|
| 2026-04-24 | Codex | Claude lead | Handoff channel | Use `SPRINT.md` as the only durable sprint communication channel. | Active |

Accepted handoff targets:

- Active ticket state: update `Active Sprint Board`.
- Blocking issue: update `Blocker Log`.
- Process or graph decision: update `Decision Log`.
- Cross-system operational note: update `Control Plane Handoff`.

Do not add operational notes to ticket bodies unless the ticket specification itself must change.

## Codex Escalation Threshold

Codex is not a routine reviewer for every worker result. Claude-side `nbb-reviewer` owns normal ticket review. Codex should intervene only when there is a severe direction risk or the human operator asks for a second opinion.

Escalate to Codex for:

- hard dependency or DAG contradictions;
- security or production-safety regressions;
- raw-code analysis, auth, permission, RLS, or data-isolation concerns;
- repeated worker/reviewer disagreement;
- merge conflicts that require architecture judgment;
- evidence that agents are drifting from locked ticket decisions;
- a proposed ticket/spec change that affects downstream scheduling;
- phase-gate readiness decisions before broad parallel execution.

Do not escalate to Codex for:

- style preferences already covered by the ticket body;
- minor wording polish;
- local implementation details inside the ticket's accepted scope;
- test skips that `nbb-reviewer` accepts with a concrete reason;
- single-ticket issues that Claude-side review can resolve directly.

## Agent Lanes

| Lane | Primary ownership | Typical tickets |
|---|---|---|
| Foundation and CI | repo docs, CI, guardrails, smoke tests | `NBB-101`, `NBB-102`, `NBB-103`, `NBB-106`, `NBB-107`, `NBB-109` |
| Policy and contracts | auth, permissions, contracts, providers/connectors, loaders | `NBB-201` through `NBB-208B`, `NBB-210` |
| Stores and mechanical moves | former `data_services`, refactory move execution | `NBB-209A` through `NBB-209E` |
| Chat | chat public surface, loop split, chat tools | `NBB-301` through `NBB-304`, `NBB-701` |
| Sources and analysis | source skeleton, ingestion/citation moves, analysis slices | `NBB-401` through `NBB-403`, `NBB-702` |
| Studio | taxonomy, registry, layer map, item migrations | `NBB-501A` through `NBB-507`, `NBB-703` |
| Frontend | shell rules, hooks/providers, lib/context tightening | `NBB-601` through `NBB-604` |
| Verification and cleanup | architecture checks, utility drains, final cleanup | `NBB-704A` through `NBB-706` |

## Phase Plan

### Phase 1 - Serial Foundation

Run first and do not parallelize:

```text
NBB-101 -> NBB-102
```

Purpose:

- Remove stale branch/repo guidance before contributors begin.
- Make current structure rules override old mechanism-first docs.

Exit gate:

- `NBB-101` and `NBB-102` merged to `develop`.
- No active guidance tells agents to work from stale branch or fork instructions.

### Phase 2 - Foundation Fanout

Run after `NBB-102`:

```text
NBB-103
NBB-104
NBB-105
```

Purpose:

- `NBB-103`: CI, no-new-legacy guardrail, refactory workflow.
- `NBB-104`: backend roots, charters, dependency-direction rules.
- `NBB-105`: frontend shell and ownership skeleton.

Exit gate:

- CI exists and can run the early guardrails.
- Backend destination roots and route-adapter policy exist.
- Frontend shells are documented before frontend moves begin.

### Phase 3 - Safety and Contract Wall

Run after Phase 2 gates, according to exact dependencies:

```text
NBB-106
NBB-107
NBB-108A
NBB-109
NBB-203
NBB-204
NBB-205
NBB-206
NBB-207A
NBB-208A
NBB-601
```

Purpose:

- Add baseline route/auth/correctness tests.
- Quarantine raw-code analysis.
- Define data, cross-stack, provider/connector, and loader boundaries.

Exit gate:

- Route smokes and auth tests cover migration-critical behavior.
- `NBB-203` prevents production raw-code analysis.
- `NBB-207A` loader compatibility lands before prompt/tool JSON movement.

### Phase 4 - Sliced Policy, Stores, and Early Drains

Run as dependencies clear:

```text
NBB-201
NBB-202A
NBB-202B
NBB-207B
NBB-207C
NBB-208B
NBB-209A
NBB-209B
NBB-209C
NBB-209D
NBB-209E
NBB-210
NBB-401
NBB-602
NBB-603
NBB-604
NBB-704A
NBB-705A
NBB-705C
```

Important sequencing:

- `NBB-207C` waits on `NBB-203` because analysis tool schemas must not move before raw-analysis quarantine.
- `NBB-202B` waits on `NBB-202A`, `NBB-206`, and `NBB-207C`.
- `NBB-209A` waits on `NBB-109` so the chat N+1/cost fixes land before the chat store move.
- `NBB-705C` intentionally runs early because it is an owner-specific provider utility drain.

### Phase 5 - Domain Streams

Run lanes independently once their exact dependencies merge.

Chat:

```text
NBB-301 -> NBB-302 -> NBB-303 -> NBB-701
                 \-> NBB-304
```

Sources:

```text
NBB-401 -> NBB-402 -> NBB-702
NBB-401 + NBB-202B + NBB-203 + NBB-207A/B/C -> NBB-403 -> NBB-702
```

Studio:

```text
NBB-501A -> NBB-501B -> NBB-502 -> NBB-503 -> NBB-504
                                                  -> NBB-505
                                                  -> NBB-506
                                                  -> NBB-507
```

Frontend:

```text
NBB-601 + NBB-108A -> NBB-602
NBB-601 + NBB-108A + NBB-205 -> NBB-603
NBB-602 + NBB-603 + NBB-108A -> NBB-604
```

### Phase 6 - Verification, Utility Drains, and Final Cleanup

Verification:

```text
NBB-303 -> NBB-701
NBB-402 + NBB-403 -> NBB-702
NBB-502 + NBB-503 + NBB-210 -> NBB-703
NBB-704A + NBB-302 + NBB-402 + NBB-503 + NBB-603 -> NBB-704B
```

Utility drains:

```text
NBB-201 + NBB-209C -> NBB-705A
NBB-402 + NBB-403 -> NBB-705B
NBB-205 + NBB-206 + NBB-208A -> NBB-705C
NBB-502 + NBB-503 + NBB-504 + NBB-506 -> NBB-705D
NBB-705A + NBB-705B + NBB-705C + NBB-705D -> NBB-705E
```

Final gates:

```text
NBB-704B + NBB-109 + NBB-705E -> NBB-704C
NBB-701 + NBB-702 + NBB-703 + NBB-704B + NBB-704C + NBB-705E -> NBB-706
```

## Critical Path

The longest weighted path currently runs through studio/background/utility cleanup:

```text
NBB-101 -> NBB-102 -> NBB-104 -> NBB-204 -> NBB-210
-> NBB-501B -> NBB-502 -> NBB-503 -> NBB-504
-> NBB-705D -> NBB-705E -> NBB-704C -> NBB-706
```

Do not let `NBB-204`, `NBB-210`, `NBB-501B`, `NBB-502`, or `NBB-503` sit idle once unblocked.

## Refactory Workflow

Use refactory for movement tickets named in `REFACTORY_SETUP.md`.

Per operation:

1. Confirm `tool_search` exposes `mcp__refactory__move_module`.
2. For `move_symbol`, create the target module first.
3. Run the refactory operation with `dry_run=true`.
4. Review the preview and affected files.
5. Run the same operation with `dry_run=false`.
6. Append a row to `docs/tickets/move-plan.csv`.
7. Run `docs/tickets/helpers/string_ref_scan.py <old_path-or-pattern>`.
8. Run `mcp__refactory__validate_imports`.
9. Run the ticket's verification commands.

Do not use refactory execution tools in `NBB-706`; that ticket is verification and manual cleanup only.

## PR Checklist

Every ticket PR must include:

- Ticket key and title.
- Dependency evidence: which upstream tickets are merged.
- Primary write scope touched.
- Whether refactory was used.
- `move-plan.csv` rows added, if applicable.
- Tests and checks run.
- Any skipped checks with reason.
- Any discovered contradiction, and the ticket/deferred-doc patch that resolved it.

## Merge Order

1. Merge serial foundation first: `NBB-101`, then `NBB-102`.
2. Merge independent fanout tickets as soon as green.
3. Prefer merging graph-unlocking P0 tickets before P1 cleanup tickets.
4. Prefer small mechanical store moves before large domain splits if both are unblocked.
5. Never merge a dependent ticket before its hard-gate ticket is on `develop`.

## Verification Ladder

Use the narrowest required check during active development, then broaden before merge.

| Level | When | Commands |
|---|---|---|
| Graph docs | Any ticket doc edit | `python docs/tickets/dag.py --check` |
| Refactory safety | Any mechanical move | `mcp__refactory__validate_imports` plus `string_ref_scan.py` |
| Backend focused | Backend behavior touched | targeted `pytest` files |
| Backend broad | Route/auth/core migration touched | `cd backend && pytest` when feasible |
| Frontend focused | Frontend ownership touched | `cd frontend && npm run build` or chosen `NBB-108A` test command |
| Final cleanup | `NBB-704C` and `NBB-706` | pyright, AST verifiers, backend tests, frontend build if touched |

## Active Sprint Board

Update this table when work starts, merges, or blocks.

| Ticket | Lane | Status | Owner | Worker branch/worktree | Reviewer | Merge commit | Checks | Notes |
|---|---|---|---|---|---|---|---|---|
| `NBB-101` | Foundation and CI | Merged | top-level dispatcher | `worktree-agent-ab1316b6b8b3c4fa8` / cleaned up | `MERGE` | `683173c` | PASS worker/reviewer checks; PASS merge/push cleanup | Merged to `origin/main`; backup branches preserved. |
| `NBB-102` | Foundation and CI | Merged | top-level dispatcher | `worktree-agent-a212eb3d66f0839f7` / cleaned up | `MERGE` | `0c31b21` | PASS worker/reviewer checks; PASS merge/push cleanup | STRUCTURE.md published; placement checklist + frozen list locked. |
| `NBB-103` | Foundation and CI | Merged | top-level dispatcher | `worktree-agent-a23dc37d5c5369c2f` / cleaned up | `MERGE` | `df44200` (non-ff, ran parallel with `NBB-105`) | PASS worker/reviewer checks; PASS merge/push cleanup; SKIP refactory MCP dry-run smoke | `.github/workflows/` + structural guardrail + explicit allowlist landed. `mcp__refactory__*` tools were not visible in the worker session, so the dry-run smoke was skipped; investigate MCP-plugin availability in spawned worker sessions before dispatching Wave 4 movement tickets. |
| `NBB-104` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a7f6352a32780bf16` / cleaned up | `MERGE` | `b12bf50` | PASS worker/reviewer checks; PASS merge/push cleanup | 11 new backend roots + api charter + STRUCTURE.md extensions; locked Placement Checklist + Frozen Destinations blocks preserved. |
| `NBB-105` | Frontend | Merged | top-level dispatcher | `worktree-agent-a5073d03b5e885c14` / cleaned up | `MERGE` | `54a6568` (fast-forward) | PASS worker/reviewer checks; PASS merge/push cleanup | `frontend/STRUCTURE.md` published; `frontend/src/components/hooks/` marked legacy; write scope kept disjoint from `NBB-103`. |
| `NBB-106` | Foundation and CI | Ready | unassigned |  |  |  |  | Deps merged: `NBB-103` at `df44200`. Write scope: `backend/tests/`, `backend/app/api/__init__.py`, backend test fixtures/config. No refactory. Collisions: shares `backend/tests/` with `NBB-107`/`NBB-109` — serialize on shared fixtures (`conftest.py`). |
| `NBB-107` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-103` at `df44200`. Write scope: `backend/tests/`, `backend/app/api/`, `backend/app/services/auth/`, `backend/app/utils/auth_middleware.py`. No refactory. Collisions: `services/auth/rbac.py` overlaps `NBB-109` future-annotation removal — serialize against `NBB-109`. |
| `NBB-108A` | Frontend | Ready | unassigned |  |  |  |  | Deps merged: `NBB-105` at `54a6568`. Decision ticket. Write scope: `docs/tickets/DEFERRED.md`, `frontend/package.json`, frontend test config, `.github/workflows/` if CI chosen. Collisions: `DEFERRED.md` shared with `NBB-205` — serialize. If implementation chosen, the new workflow file must extend `NBB-103`'s CI setup rather than replace it. |
| `NBB-109` | Foundation and CI | Ready | unassigned |  |  |  |  | Deps merged: `NBB-103` at `df44200`. Write scope: `backend/app/services/` (project_id, chat N+1, narrow except, path_utils, future-annotation removals), `backend/app/api/chats/routes.py`, `backend/app/api/messages/routes.py`, `backend/app/utils/path_utils.py`, `backend/scripts/verify_project_id_coverage.py` (new), `backend/tests/test_claude_cost_tracking.py` (new). No refactory. Collisions: `services/auth/rbac.py` with `NBB-107`; `services/ai_agents/csv_analyzer_agent.py` + `services/tool_executors/analysis_executor.py` with `NBB-203` — serialize against `NBB-107` and `NBB-203`. |
| `NBB-203` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-103` at `df44200`. Write scope: `backend/app/services/ai_agents/csv_analyzer_agent.py`, `backend/app/services/tool_executors/analysis_executor.py`, `backend/app/services/tools/analysis_agent/`, `backend/tests/`. No refactory. Collisions: overlaps `NBB-109` on csv_analyzer_agent + analysis_executor — serialize. |
| `NBB-204` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-104` at `b12bf50`. Write scope: `backend/supabase/migrations/`, `backend/app/` domain store docs, storage bucket docs, backend access smoke checklist. No refactory. Collisions: backend package docs shared with `NBB-206` — carve charter authorship per-root (data-bearing roots vs providers/connectors) or serialize. |
| `NBB-205` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-104` at `b12bf50`. Write scope: backend contract docs/schemas, `frontend/src/lib/api/`, `backend/app/api/`, `docs/tickets/DEFERRED.md`. No refactory. Collisions: `DEFERRED.md` shared with `NBB-108A` — serialize. |
| `NBB-206` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-104` at `b12bf50`. Write scope: `backend/app/providers/`, `backend/app/connectors/`, backend package charters, structure/dependency docs. No refactory. Collisions: backend package docs shared with `NBB-204` — coordinate per-root or serialize. |
| `NBB-207A` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-104` at `b12bf50`. Write scope: `backend/app/config/tool_loader.py`, `backend/app/config/prompt_loader.py`, loader tests, prompt/tool registry config. No refactory (shims, not moves). Collisions: none in Phase 3 (verified `backend/app/config/` has no `from __future__` annotations NBB-109 would touch). Unlocks `NBB-207B`, `NBB-207C`. |
| `NBB-208A` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-104` at `b12bf50`. Write scope: `backend/app/__init__.py`, `backend/app/api/settings/api_keys.py`, `backend/app/services/app_settings/`, provider/connector config reload hooks. No refactory. Collisions: `services/app_settings/` potentially intersects `NBB-109` future-annotation sweep — confirm with worker and serialize if needed. |
| `NBB-601` | Frontend | Ready | unassigned |  |  |  |  | Deps merged: `NBB-105` at `54a6568`. Write scope: `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/lib/`, `frontend/src/contexts/`, frontend placement docs. No refactory (docs-only; `NBB-602` does moves). Collisions: none in Phase 3. |

Status values:

- `Ready`
- `In progress`
- `Review`
- `Ready to merge`
- `Merged`
- `Blocked`
- `Deferred`

Reviewer values:

- blank: no worker result yet;
- `Pending`: worker passed and review has not completed;
- `MERGE`: reviewer says safe to merge;
- `DO_NOT_MERGE`: reviewer found blocking issues;
- `BLOCKED`: review could not establish merge safety.

Checks cell format:

```text
PASS <short command>; SKIP <short command> - <reason>; FAIL <short command> - <reason>
```

## Blocker Log

| Date | Ticket | Blocker | Resolution owner | Status |
|---|---|---|---|---|
| 2026-04-24 |  |  |  |  |

## Decision Log

| Date | Decision | Owner |
|---|---|---|
| 2026-04-24 | Sprint uses `tickets.csv` task dependencies as hard scheduling gates; this file coordinates execution only. | Lead integrator |
| 2026-04-24 | Refactory is required for movement tickets unless the ticket explicitly marks the work manual. | Lead integrator |
| 2026-04-24 | `NBB-404` remains deferred through `D-002`; production raw-code analysis stays disabled. | Sources/security owner |
| 2026-04-24 | Investigate `mcp__refactory__*` tool availability in spawned worker sessions before dispatching Wave 4 movement tickets. `NBB-103`'s refactory dry-run smoke was skipped because the tools were not visible in the worker session; movement tickets (`NBB-201`, `NBB-209A`–`E`, `NBB-402`, `NBB-505`, `NBB-602`–`604`, etc.) depend on the plugin being loadable there. Likely fix is ensuring the worker's `.mcp.json` or plugin-dir configuration is present in each isolated worktree; otherwise movement work will regress to manual `git mv`. | Lead integrator |

## Done Criteria for the Sprint

The sprint is complete when:

- `NBB-706` is merged.
- `docs/tickets/dag.py --check` passes.
- `move-plan.csv` accounts for every mechanical move that landed.
- No forwarding-only compatibility modules remain without documented reason.
- Final backend architecture docs describe the migrated truth.
- `DEFERRED.md` still names all known out-of-scope work and guardrails.
