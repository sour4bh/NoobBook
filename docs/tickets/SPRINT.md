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

As of 2026-04-25, Phase 4/5 batch 9 partial (NBB-209C merged; 504/505/506 in flight):

- Branch: `main` @ `dd0ebb5`
- Merged progress: 37 of 59 tasks merged (Phase 1-3 complete; Phase 4 batch 1: NBB-208B, NBB-401, NBB-704A; batch 2: NBB-209D, NBB-209B; batch 3: NBB-209E, NBB-207B; batch 4: NBB-207C, NBB-210; batch 5: NBB-501A, NBB-209A; batch 6: NBB-501B, NBB-402; batch 7: NBB-502, NBB-201; batch 8: NBB-202A, NBB-503; batch 9 complete: NBB-209C, NBB-506, NBB-504, NBB-505)
- Batch 9 in flight: NBB-504 (branch `worktree-agent-a68fed249799ef2f4`, 4 commits at `0a54208`), NBB-505 (branch `worktree-agent-a6eab7044d857613b`, 4 commits at `4360ade`), NBB-506 (branch `worktree-agent-a705f75053b604cce`, completed PASS at `ab14993`). NBB-209C merged at `2302823` unblocked NBB-705A. NBB-507/202B/602/603/705C queued for batch 10.
- **Contamination event 2026-04-25**: main checkout accumulated partial NBB-504 blog-item moves + NBB-505 ad-item moves during batch 9 execution (strict subset of worker branches; no unique data lost). Stashed at `stash@{0}` for forensic preservation; worker-branch merges will apply full correct state. Suspected cause: refactory MCP's `project_root` resolution leaked into main checkout on each worker's FIRST move (subsequent items stayed isolated). Investigate before batch 10 dispatch — likely affects all future parallel movers.
- Phase 5 studio lane opens (NBB-503 pilot proves the 5-file pattern; NBB-504–507 can copy).
- Graph shape: 66 CSV rows, 7 epics, 59 tasks
- Graph validation: `python docs/tickets/dag.py --check`
- Refactory plugin: required for movement tickets; verify each session with `tool_search` for refactory's `move_module` — either `mcp__refactory__move_module` (raw `.mcp.json` load) or `mcp__plugin_refactory_refactory__move_module` (`--plugin-dir` plugin-framework load)
- Permanent raw-code analysis replacement: out of scope, tracked by `D-002`
- Route movement out of `backend/app/api`: out of scope, tracked by `D-001`

## Execution Rules

1. A task may start only when every task in its `depends_on` field has merged to `main`.
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

- Keep `main` green.
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
5. Never merge a dependent ticket before its hard-gate ticket is on `main`.

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
| `NBB-106` | Foundation and CI | Merged | top-level dispatcher | `worktree-agent-a55498584830066db` / cleaned up | `MERGE` | `efd8b5a` (non-ff merge of `9a67954`) | PASS worker/reviewer checks; PASS merge/push cleanup | 11 blueprints covered by route smokes; chats/messages blueprints split out; 404 control case included; narrow test fixtures. Worker surfaced the `backend/config.py` (dict) vs `backend/app/config/` (subpackage) name collision — worked around via test conftest shim; flagged for later structural fix (see Decision Log). |
| `NBB-107` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-abe899838a3b52615` / cleaned up | `MERGE` | `9516788` (non-ff of `f2e5efc`) | PASS worker/reviewer checks; PASS merge/push cleanup | 29 new auth/permissions tests landed covering token validation, query-token allowlist, project-access, default-user fallback, and `PermissionsService` fail-open behavior; fail-open behavior captured in tests but intentionally **not** tightened (that is `NBB-202A`'s work); `backend/config.py` vs `backend/app/config/` collision shim mirrored from `NBB-106` in the test conftest (per Decision Log flag-not-fix rule). |
| `NBB-108A` | Frontend | Merged | top-level dispatcher | `worktree-agent-a44ae52fe74d7b098` / cleaned up | `MERGE` | `6bdeb81` (fast-forward) | PASS worker/reviewer checks; PASS merge/push cleanup | Deferral chosen; `docs/tickets/DEFERRED.md` `D-004` records owner (frontend owner) and minimum follow-up scope for `NBB-108B` re-entry; `frontend/package.json`, frontend test config, and `.github/workflows/` untouched. |
| `NBB-109` | Foundation and CI | Merged | top-level dispatcher | `worktree-agent-a5d65693e10846b1e` / cleaned up | `MERGE` | `465b676` (non-ff of `37d0ce4`+`04b4163`) | PASS worker/reviewer checks; PASS merge/push cleanup; SKIP `backend/tests/test_cost_tracking.py::test_unknown_model_uses_sonnet_pricing`, `backend/tests/test_asset_registry.py::test_public_register_helpers_exported_from_package` (preexisting, unrelated; deselected) | 17 `from __future__ import annotations` removed; chat listing N+1 fixed; bare-except at `api/chats/routes.py:103` + `api/messages/routes.py:103` narrowed; `backend/scripts/verify_project_id_coverage.py` + `backend/tests/test_claude_cost_tracking.py` shipped; `backend/config.py` vs `backend/app/config/` name collision re-confirmed and flagged — not fixed in this ticket (see Blocker Log). |
| `NBB-203` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a8a8c0a12f5270c8f` / cleaned up | `MERGE` | `353cb4b` (non-ff of `ca211be`) | PASS worker/reviewer checks; PASS merge/push cleanup | Defense-in-depth flag gate (`NOOBBOOK_AUTH_REQUIRED=false` AND `NOOBBOOK_ALLOW_RAW_ANALYSIS=true`) enforced at both `analysis_executor.py` and `csv_analyzer_agent.py` boundaries; 20 new security/analysis tests cover auth-required mode + dev-mode-without-flag + dev-mode-with-flag; permanent declarative-analysis replacement stays deferred under `D-002`. |
| `NBB-204` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a9dd698b03ca52b8a` / cleaned up | `MERGE` | `86012e4` (non-ff of `c9bf122`+`b1e8a94`) | PASS worker/reviewer checks; PASS merge/push cleanup | `backend/OWNERS.md` + `backend/STORAGE_CONTRACTS.md` + 6 per-root `CHARTER.md` overlays (projects, chat, sources, studio, brand, background) + `data_access_smoke` checklist shipped; storage RLS inconsistency documented for `NBB-502`/`NBB-503` follow-up; `path_utils.py` kept out of scope per ticket. Auth-required precondition noted on the backend project guard. |
| `NBB-205` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a75b0953335aa3b8d` / cleaned up | `MERGE` | `6273f9c` (non-ff of `d500818`+`eedde5b`) | PASS worker/reviewer checks; PASS merge/push cleanup | 15 cross-stack contracts catalogued (14 required by ticket body + bonus `chats.selected_source_ids`); each entry traced to backend owner, frontend consumer, migration/route/schema primary source, minimum contract test, valid/production/invalid examples where applicable. |
| `NBB-206` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-ad6cbeb9f9aa5a7d8` / cleaned up | `MERGE` | `1057959` (fast-forward from `ec78bdf`) | PASS worker/reviewer checks; PASS merge/push cleanup | 5 files touched with 9-section coverage per charter; locked Placement Checklist + Frozen Destinations blocks preserved; platform/files rejected. Notes: Google subtree split into `auth`/`imagen`/`video` → `providers/` and `drive` → `connectors/`; MCP split into `client` → `providers/` and `tool_service`+`connection` → `connectors/`; Supabase storage flagged as domain-reviewed provider seam. |
| `NBB-207A` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a3deaddbb8ed466ca` / cleaned up | `MERGE` | `a41ea8f` (non-ff merge of `7cfc400`) | PASS worker/reviewer checks; PASS merge/push cleanup | Introduced `asset_registry` + loader shims in `backend/app/config/{prompt_loader.py,tool_loader.py}`; 13 loader tests pass; public APIs preserved; new registry seams prepared for `NBB-207B`/`NBB-207C`. |
| `NBB-208A` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a71892548793105ce` / cleaned up | `MERGE` | `e8a6ea2` (non-ff of `5378663`) | PASS worker/reviewer checks; PASS merge/push cleanup | Validator-ownership map published in `backend/app/api/settings/api_keys.py` module header (each `API_KEYS_CONFIG` entry maps to its validator, reload hook, and intended provider/connector destination); added `ClaudeService.reload_config()` so Anthropic + Opik reload symmetrically with `notion_service`, `jira_service`, `freshdesk_service`, `mixpanel_service`; `.env` reload (`EnvService.reload_env`) and service reload semantics documented; charter authorship for `providers/`/`connectors/` intentionally reserved for `NBB-206`. |
| `NBB-601` | Frontend | Merged | top-level dispatcher | `worktree-agent-a6a4af4f47fe196e7` / cleaned up | `MERGE` | `0b09d4b` (fast-forward) | PASS worker/reviewer checks; PASS merge/push cleanup | Shell charters published for all four frontend shells + `ui/`; feature-owned anti-examples enumerated; legacy marker for `frontend/src/components/hooks/` reinforced. |
| `NBB-201` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a5ad001db71282172` / cleaned up | `MERGE` | `6aeeffc` (non-ff of `46a248e`) | PASS worker/reviewer checks; PASS merge/push cleanup; 338 full-suite passed, 2 deselected | Auth consolidation landed in 8 commits (5 refactory ops + 3 semantic + manual repair). Cat B hit 26 sites (auth decorator rewrites); Cat A=0, Cat C=0. Barrel at `services/auth/__init__.py` gutted; rbac.py thin re-export shim (NBB-706 cleanup). **NEW rope-hostile category discovered: Blueprint init reordering** — rope hoisted `from app.api.<bp> import routes` above `Blueprint()` in 6 `api/**/__init__.py` files; worker re-ordered to preserve Flask startup. Query-token allowlist narrowed to browser media routes. 30 auth tests (up from 29). Commit 8 of 9 (data-services policy removal) scoped down to docstring-only; full removal deferred to NBB-705A. Unblocks NBB-202A, NBB-209C, NBB-705A. |
| `NBB-202A` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a5cb95c0e94f269af` / cleaned up | `MERGE` | `872d18a` (non-ff of `8fb76f2`) | PASS worker/reviewer checks; PASS merge/push cleanup | Typed PERMISSION_TAXONOMY at `backend/app/auth/permissions.py:53-103`; `_fallback_allow()` denies in auth-required mode, allows in `NOOBBOOK_AUTH_REQUIRED=false`. Unknown category/item short-circuit before DB I/O. DB failure fails closed in auth-required + logs warning. Intentional asymmetry: `get_user_permissions()` returns defaults on DB error (admin UI); `user_has_permission()` denies. 38 auth tests (up from 30), 346 full-suite passes. Frontend `PermissionsContext.tsx` comment-only (UI-only trust note). Caller-side gap at `main_chat_service.py:149-172` flagged for NBB-202B. Unblocks NBB-202B + NBB-209C chain. |
| `NBB-202B` | Policy and contracts | Ready | unassigned |  |  |  |  | Deps merged: `NBB-202A` at `872d18a`, `NBB-207C` at `de4bf76`, `NBB-206` at `1057959`. ToolCapabilityPolicy for Claude-visible tools. Caller-side gap flagged at `main_chat_service.py:149-172` by NBB-202A worker — `not user_id or user_has_permission(...)` short-circuits when `user_id=None`. |
| `NBB-207B` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a9d5cffbd6d12201f` / cleaned up | `MERGE` (1 P3 cosmetic: off-by-one prompt count in NOTES) | `76ee334` (non-ff of `058cc99`) | PASS worker/reviewer checks; PASS merge/push cleanup | 5 prompts moved to `sources/{pdf,pptx,image,link,analysis/research}/prompts/`; 26 deferred to downstream tickets; 1 `default_prompt` shared-loader default. 10 move-plan rows (5 json_asset_move + 5 text_reference_check). Real bug fixed: `PromptLoader.list_all_prompts` now walks registered dirs + legacy with dedup (was missing moved prompts from `/prompts/all` route). Production registration via `asset_registry._PRODUCTION_PROMPT_PATHS` called from `backend/app/config/__init__.py`. Merge conflict on move-plan.csv vs NBB-209E resolved by keeping both sections. |
| `NBB-207C` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a42bff32b01b55046` / cleaned up | `MERGE` | `de4bf76` (non-ff of `06da95f`) | PASS worker/reviewer checks; PASS merge/push cleanup | 5 tool families moved to `sources/{pdf,pptx,image,link,analysis/research}/tools/` (9 JSON files); 16 families deferred (chat/studio/analysis/connector skeletons not yet present); `_PRODUCTION_TOOL_PATHS` extended in `asset_registry.py` via unified `register_production_asset_paths()`; zero Python consumer rewrites (tool_loader resolves via registry); 14 move-plan rows. Unblocks NBB-501A. |
| `NBB-208B` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-ac94071c62e316930` / cleaned up | `MERGE` | `9e7fe6a` (non-ff of `6f54935`) | PASS worker/reviewer checks; PASS merge/push cleanup | New `docs/deployment/observability.md` + comment-only pointers in `backend/gunicorn.conf.py`, `frontend/nginx.conf`, `backend/app/__init__.py`. No code behavior change; documentation-only boundary inventory. |
| `NBB-209A` | Stores and mechanical moves | Merged | top-level dispatcher | `worktree-agent-a508ebc447ef924e2` / cleaned up | `MERGE` | `2ef4bfc` (non-ff of `7a36fd2`) | PASS worker/reviewer checks; PASS merge/push cleanup (resolved main_chat_service.py + move-plan.csv conflicts with NBB-210) | Moved chat_service.py → chat/store.py (ChatService→ChatStore) + message_service.py → chat/message/store.py (MessageService→MessageStore). 4 move-plan rows. Manual repair triggered: chat_service hit ALL THREE rope-hostile categories (A: hoisted lazy in cost_tracking.py:80-83; B: body-rewrite to module-attribute; C: shim-form eager rewrite at api/chats/routes.py 6 sites + main_chat_service.py 3 sites); message_service hit Cat C only (14 files — main_chat_service.py + 13 ai_agents/*). 21 files touched. Re-export shim at data_services/__init__.py preserves backward-compat. |
| `NBB-209B` | Stores and mechanical moves | Merged | top-level dispatcher | `worktree-agent-a946d0446a5b997bb` / cleaned up | `MERGE` | `79d469e` (non-ff of `d8bee5c`) | PASS worker/reviewer checks; PASS merge/push cleanup; PASS full backend pytest (296 passed, 2 deselected preexisting) | Five commits: dead-singleton removal (`32a13f3`), refactory apply (`48dcef1`), authorized manual repair of 5 lazy-import sites + 6 eager call-sites (`6b166c5`), singleton consolidation to `projects/store.py` (`b11dda5`), move-plan.csv rows (`d8bee5c`). 17 files changed. All tests green (12 smoke, 29 auth, 296 full). Decision Log 2026-04-24 "NBB-209B: bounded one-ticket manual repair" records the authorized exception. |
| `NBB-209C` | Stores and mechanical moves | Merged | top-level dispatcher | `worktree-agent-ac3d0e3377b67add3` / cleaned up | `MERGE` | `2302823` (non-ff of `4a15d2f`) | PASS worker/reviewer checks; PASS merge/push cleanup; PASS full backend pytest (345 passed, 2 deselected); PASS verify_architecture.py | Moved `user_service.py → auth/user/store.py` (UserService→UserStore) + `password_utils.py → auth/password.py`. 4 move-plan rows. **Zero Cat A/B/C hostility** — `get_user_service()` factory indirection protected all 4 consumer sites (cost_tracking.py :300/:357 lazy imports stayed in-function; api/settings/users.py + data_services/__init__.py untouched for class rename). Clean automated path. Refactory required a 2-op `move_module` split for user_service (same-basename relocate + in-dir rename `user_service.py`→`store.py`) due to basename change; intermediate path never committed. Singleton consolidated to one `_user_service` + `get_user_service()` factory at `auth/user/store.py`. Re-export shim at `data_services/__init__.py` preserved for NBB-706 cleanup. Unblocks NBB-705A. |
| `NBB-209D` | Stores and mechanical moves | Merged | top-level dispatcher | `worktree-agent-af10314bc6d887496` / cleaned up | `MERGE` | `9f18494` (non-ff of `a540a60`) | PASS worker/reviewer checks; PASS merge/push cleanup; SKIP full backend pytest (not required by ticket) | Brand asset + config stores moved to `backend/app/brand/{asset,config}/store.py` with class renames `BrandAssetService→BrandAssetStore`, `BrandConfigService→BrandConfigStore`. 4 move-plan rows. One minimal manual fix at `api/brand/routes.py` for a local-name basename collision (two `from X.store import store` shadowed). Singleton names `brand_asset_service`/`brand_config_service` preserved. Re-exports at `data_services/__init__.py` kept as backward-compat shim. |
| `NBB-209E` | Stores and mechanical moves | Merged | top-level dispatcher | `worktree-agent-a28add90740d1f1bc` / cleaned up | `MERGE` | `21b094d` (non-ff of `7fdbdc5`) | PASS worker/reviewer checks; PASS merge/push cleanup | `database_connection_service` + `mcp_connection_service` moved to `connectors/{database,mcp}/connection/store.py` with class renames (`*Service` → `*Store`). 4 move-plan rows. MCP's 2 lazy in-function imports in `mcp_tool_service.py:65,:137` were handled correctly by rope this time (no manual repair needed). Re-export shim in `data_services/__init__.py` fixes asymmetric base-state bug (mcp wasn't re-exported). |
| `NBB-210` | Policy and contracts | Merged | top-level dispatcher | `worktree-agent-a6485fbf941ffafde` / cleaned up | `MERGE` | `d3457c4` (non-ff of `6edd21a`) | PASS worker/reviewer checks; PASS merge/push cleanup; PASS full backend pytest (308 passed, 2 deselected); PASS verify_architecture.py | `task_service.py → background/tasks.py` (partition deferred — `status/cancel/logs` require semantic splits, out of mechanical-move scope; `active_tasks.py` already route-owned). 37 consumer rewrites. Manual repair applied for TWO rope-hostile categories (A: hoisted lazy imports — 14 sites; B: eager shim-form rewritten to module-attribute `tasks.method()` — 13 sites). Singleton `task_service` name preserved. Re-export shim preserved at `services/background_services/__init__.py`. Critical-path cleared — unblocks NBB-501B, NBB-502, NBB-503, NBB-703. |
| `NBB-401` | Sources and analysis | Merged | top-level dispatcher | `worktree-agent-a61b82a5209584c11` / cleaned up | `MERGE` | `5bbf9d5` (non-ff of `b592272`) | PASS worker/reviewer checks; PASS merge/push cleanup | Extended `backend/app/sources/CHARTER.md` with NBB-401 file-format ownership map; new `backend/app/sources/README.md`; 10 skeleton `__init__.py` markers at `sources/{upload,pdf,pptx,docx,image,link,youtube,audio,analysis,research}/`. Unblocks NBB-402 and the whole sources lane. |
| `NBB-402` | Sources and analysis | Merged | top-level dispatcher | `worktree-agent-a28e168be7d25c5a7` / cleaned up | `MERGE` (1 P3 stale line-number reference) | `aca375b` (non-ff of `5b5f65c`) | PASS worker/reviewer checks; PASS merge/push cleanup; PASS full backend pytest (337 passed, 2 deselected); PASS verify_architecture.py | 7-row refactory moved source_service/source_processing_service/source_index_service/file_upload.py + 3 utils drains (file/citation/source_content) to `backend/app/sources/` (`catalog.py`, `pipeline.py`, `index.py`, `upload/file.py`, `file_contract.py`, `citations.py`, `content.py`). 2 renames (SourceService→SourceCatalog, SourceProcessingService→SourcePipeline). 54 files changed. 12 move-plan rows. Manual repair: 25 Cat B sites + 6 Cat C sites (no Cat A). New shim pattern: `__getattr__` lazy re-export at `services/source_services/__init__.py` (circular import required non-eager shim; NBB-706 owns removal). Unblocks NBB-702, NBB-705B, NBB-704B. |
| `NBB-501A` | Studio | Merged | top-level dispatcher | `worktree-agent-a2e88760d7e174575` / cleaned up | `MERGE` (1 P3 wording polish) | `b41a791` (non-ff of `2d6b65a`) | PASS worker/reviewer checks; PASS merge/push cleanup | New `backend/app/studio/TAXONOMY.md` (5 categories × 19 items, locked verbatim from decision map) + `backend/app/studio/README.md`. 16 studio tool rows aligned with NBB-207C; `read_source_content.json` correctly listed as sources-owned. Logo-generation in `studio/design/logo/`, brand asset/config under `brand/`. `logo_utils.py` placement deferred to NBB-502/NBB-506. Unblocks NBB-501B. |
| `NBB-503` | Studio | Merged | top-level dispatcher | `worktree-agent-aa795b1ee4c5f7b8d` / cleaned up (+ 2 prior abandoned: `a37d598b66f3ef063` stream-timeout, `ac691edbc00fd9abf` P1-rejected) | `MERGE` (after stream-timeout + 1 DO_NOT_MERGE cycle on entrypoint naming) | `4980de5` (non-ff of `db9003a`) | PASS worker/reviewer checks; PASS merge/push cleanup; 7 pilot tests + 345 full-suite | Pilot: `design/website` carved into `backend/app/studio/design/website/{build,job,run,tool}.py` + prompts/ + tools/. Legacy deleted: services/ai_agents/website_agent_service.py + services/tool_executors/website_{tool,agent}_executor.py + services/studio_services/jobs/website_jobs.py. Class renames: WebsiteAgentService→WebsiteBuilder, WebsiteAgentExecutor→WebsiteRunner, WebsiteToolExecutor→WebsiteDispatcher; method: `execute_tool`→`dispatch` (LAYER_MAP lock). 20 move-plan rows. Stream-timeout recovery preserved work via dispatcher-commit. First recovery rejected on P1 (kept `execute_tool()` entrypoint); recovery-2 fixed entrypoint naming. Unblocks NBB-504/505/506/507 studio migrations + NBB-703 verification. |
| `NBB-501B` | Studio | Merged | top-level dispatcher | `worktree-agent-a28e132905d39f075` (redo) / cleaned up; prior rejected branch `worktree-agent-af69fbe44df5f1d3e` cleaned up | `MERGE` (after 1 DO_NOT_MERGE cycle — reviewer flagged 3 P2 prompt-ownership drifts vs NBB-207B; redo worker seeded from prior branch + applied inline reconciliation notes to exactly 3 rows) | `ed257a5` (non-ff of `7f11f05`) | PASS worker/reviewer checks; PASS merge/push cleanup; PASS both worktree cleanups | New `backend/app/studio/REGISTRY.md` (381 lines, 19 items matching TAXONOMY). Reconciliation notes flag category drift for infographic (NBB-207B says `studio/design/`, TAXONOMY locks `studio/marketing/`) — needs follow-up NBB-207B sweep + NBB-505 final placement. Unblocks NBB-502 (layer mapping). |
| `NBB-502` | Studio | Merged | top-level dispatcher | `(worktree cleaned up; batch 7)` | `MERGE` | `5654c82` (non-ff of `32cd641`) | PASS worker/reviewer checks; PASS merge/push cleanup | Docs-only: new `backend/app/studio/LAYER_MAP.md` (355 lines) + `CHARTER.md` addition + `README.md` update (3 files, 360 insertions). Maps service/job/tool/run verb table for all 19 studio items per TAXONOMY (NBB-501A). Locks METHOD entrypoint-name invariants which surfaced downstream as the NBB-503 P1 reviewer rejection trigger (class rename alone is insufficient; METHOD must rename too). Unblocks NBB-503 pilot + NBB-504/505/506/507 item migrations. |
| `NBB-602` | Frontend | Ready | unassigned |  |  |  |  | Deps merged: `NBB-601` at `0b09d4b`, `NBB-108A` at `6bdeb81`. Move feature-owned hooks/providers under owning domains. |
| `NBB-603` | Frontend | Ready | unassigned |  |  |  |  | Deps merged: `NBB-601` at `0b09d4b`, `NBB-108A` at `6bdeb81`, `NBB-205` at `6273f9c`. Tighten lib/contexts/API clients/citations/logger ownership. |
| `NBB-604` | Frontend | Blocked | unassigned |  |  |  |  | Blocked on `NBB-602` and `NBB-603` (neither merged). `NBB-108A` dep satisfied at `6bdeb81`. Normalize frontend domain subtrees + design-system guardrails. |
| `NBB-704A` | Verification and cleanup | Merged | top-level dispatcher | `worktree-agent-a5c42c9b801c8ac3e` / cleaned up | `MERGE` | `d102fd4` (non-ff of `c52560b`) | PASS worker/reviewer checks; PASS merge/push cleanup | New `backend/scripts/verify_architecture.py` (root + dependency-direction checks); new `backend/STRUCTURE.md`; new CI job in `.github/workflows/ci.yml`. Enables early architecture enforcement before domain migrations complete. |
| `NBB-705A` | Verification and cleanup | Ready | unassigned |  |  |  |  | Deps merged: `NBB-201` at `6aeeffc`, `NBB-209C` at `2302823`. Drain auth utilities. NBB-201 worker deferred broader data-services policy removal here. Must preserve NBB-202A intentional asymmetry (`get_user_permissions` DB-fallback vs `user_has_permission` fail-closed) per Decision Log batch 8. |
| `NBB-705C` | Verification and cleanup | Ready | unassigned |  |  |  |  | Deps merged: `NBB-205` at `6273f9c`, `NBB-206` at `1057959`, `NBB-208A` at `e8a6ea2`. Drain provider/Anthropic utilities (Claude cost, token, media helpers). Runs early by design as an owner-specific provider utility drain. |
| `NBB-504` | Studio | Merged | top-level dispatcher | `worktree-agent-a68fed249799ef2f4` / cleaned up | `MERGE` | `8619c7f` (non-ff of `3efa60b`) | PASS worker/reviewer checks; PASS merge/push cleanup (6-file conflict resolution with 506); PASS full backend pytest (341 passed, 2 deselected); PASS verify_architecture.py; PASS import-path resolution smoke | 4 document items migrated: blog→`write.py`, business_report→`write.py`, prd→`write.py` (no run.py per LAYER_MAP), presentation→`compose.py`. 5 commits; 66 move-plan rows. **Refactory silent-apply failure on first `move_module` call (returned success=true, no files moved in worktree; subsequent calls hit cache corruption). Worker fell back to bounded-manual `git mv` + manual class/method/import rewrites for ALL 4 items.** Suspected root cause of main-checkout contamination on first-item moves (see stash@{0}). Class renames (11): *AgentService→Writer/Composer, *ToolExecutor→Dispatcher, *AgentExecutor→Runner. METHOD `execute_tool→dispatch` in 4 tool.py files. Singleton names preserved. Cat C lazy imports restored at blog/br/presentation/run.py and blogs/prds/presentations/business_reports.py routes. Second of 3 batch-9 studio merges. |
| `NBB-505` | Studio | Merged | top-level dispatcher | `worktree-agent-a6eab7044d857613b` / cleaned up | `MERGE` | `09d6d3f` (non-ff of `22b7fa9`); fix-up `dd0ebb5` | PASS worker/reviewer checks; PASS merge/push cleanup (5-file 3-way conflict with 504+506 resolved); PASS full backend pytest (337 passed, 2 deselected) after tool_executors/__init__.py stale-import fix-up; PASS verify_architecture.py | 5 marketing items migrated: ad→`create.py`, email→`write.py`, infographic→`create.py`, strategy→`plan.py`, social_post→`write.py`. 6 commits; 33 move-plan rows. **Cat A rope-hostility hit on EVERY job-module move (5/5): re-exports reordered to top; restored to bottom with comment each time.** Cat A+B on email/run.py + marketing_strategies.py. METHOD `execute_tool→dispatch` on 2 multi-tool routers. Singleton names preserved. Infographic placed at `marketing/` (TAXONOMY lock, overrides NBB-207B proposal). Double-attribute cleanup in marketing_strategies.py (from NBB-501B reconciliation). Third and final batch-9 studio merge. Post-merge fix-up `dd0ebb5` removed a stale `presentation_agent_executor` import that git's auto-merge missed. |
| `NBB-506` | Studio | Merged | top-level dispatcher | `worktree-agent-a705f75053b604cce` / cleaned up | `MERGE` | `e7860df` (non-ff of `ab14993`) | PASS worker/reviewer checks; PASS merge/push cleanup (move-plan.csv conflict with 209C resolved by concatenation); PASS full backend pytest (343 passed, 2 deselected); PASS verify_architecture.py | 4 design items migrated: component→`build.py`, flow_diagram→`build.py`, logo→`create.py` (`api/studio/logo_utils.py`→`studio/design/logo/ops.py`), wireframe→`draw.py`. 39 move-plan rows. Cat A rope-hostility: re-exports reordered back to bottom of `studio_index_service.py` with explanatory comment. METHOD `execute_tool→dispatch` applied manually to component/tool.py + wireframe/tool.py. Asset registry extended with new `_PRODUCTION_TOOL_FILE_PATHS` per-file map (2 entries). Orphan `services/ai_services/wireframe_service.py` flagged out-of-scope (dead module). Brand stores + design/website pilot untouched. **First of 3 batch-9 studio merges — 504/505 barrel conflicts expected.** |
| `NBB-507` | Studio | Ready | unassigned |  |  |  |  | Deps merged: `NBB-503` at `4980de5`. Held for batch 10 to validate 3-wide studio parallelism (504/505/506) on shared move-plan.csv + REGISTRY.md before scaling to 4-wide. Migrate learning + media items (flash_card, mind_map, quiz, audio, video). Refactory + Cat A/B/C/Blueprint-init pre-auth. |

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
| 2026-04-24 | (structural) | `backend/config.py` (plain module exposing a config dict) vs `backend/app/config/` (subpackage) name collision. Surfaced by `NBB-106` worker, re-confirmed still present by `NBB-109` worker. Suggested fix path: rename `backend/config.py` to `backend/flask_config.py` and update the 2 known import sites (`backend/app/utils/path_utils.py:29`, `backend/tests/api/conftest.py:50`). Remove the `NBB-106` test-only conftest shim as part of the fix. | backend charter follow-up | Open, not blocking any current Ready ticket. Downstream workers must flag-not-fix per Decision Log 2026-04-24 entry. |

## Decision Log

| Date | Decision | Owner |
|---|---|---|
| 2026-04-24 | Sprint uses `tickets.csv` task dependencies as hard scheduling gates; this file coordinates execution only. | Lead integrator |
| 2026-04-24 | Refactory is required for movement tickets unless the ticket explicitly marks the work manual. | Lead integrator |
| 2026-04-24 | `NBB-404` remains deferred through `D-002`; production raw-code analysis stays disabled. | Sources/security owner |
| 2026-04-24 | Investigate `mcp__refactory__*` tool availability in spawned worker sessions before dispatching Wave 4 movement tickets. `NBB-103`'s refactory dry-run smoke was skipped because the tools were not visible in the worker session; movement tickets (`NBB-201`, `NBB-209A`–`E`, `NBB-402`, `NBB-505`, `NBB-602`–`604`, etc.) depend on the plugin being loadable there. Likely fix is ensuring the worker's `.mcp.json` or plugin-dir configuration is present in each isolated worktree; otherwise movement work will regress to manual `git mv`. | Lead integrator |
| 2026-04-24 | Name collision between `backend/config.py` (plain module exposing a config dict) and `backend/app/config/` (subpackage) is a preexisting structural issue. `NBB-106`'s worker surfaced it during route smoke scaffolding and worked around it with a test-only conftest shim. A structural fix (rename one of the two, or remove the top-level `backend/config.py`) must land in a later ticket — candidates are `NBB-109` (correctness sweep, if mechanically doable without scope drift) or a dedicated follow-up scoped under the backend charters. `NBB-109`'s dispatch prompt tells the worker to flag-not-fix any encounter of this collision so it does not spawn another shim. | Lead integrator |
| 2026-04-24 | `NBB-206` incident resolved: lead Dispatch Prompt Requirements now require repo-relative paths in worker prompts; committed in `ec78bdf`. First incident (main-checkout contamination) was caught by Rule 13 and rolled back cleanly. | Lead integrator |
| 2026-04-24 | Refactory namespace investigation (from prior entry) resolved. Root cause: the `--plugin-dir` load path surfaces refactory under `mcp__plugin_refactory_refactory__*`, not `mcp__refactory__*`. Worker and reviewer specs now allowlist both namespaces; `REFACTORY_SETUP.md` documents both; the baseline self-check text accepts either. Movement tickets (`NBB-201`, `NBB-209A`–`E`, `NBB-402`, `NBB-504`–`507`, `NBB-602`–`604`, `NBB-705A`–`D`) can now dispatch without refactory blockage once their chain dependencies are merged. | Lead integrator |
| 2026-04-24 | Refactory `validate_imports` at `project_root=backend/` returns ~120 false-positive `unresolved_import_name` errors for Python stdlib (`datetime`, `decimal`, `concurrent.futures`, etc.) because rope cannot resolve stdlib without venv/sys.path wiring. Workers must scope `validate_imports` narrowly (pass `project_root` at the moved package, not `backend/`) and compare the error set against the pre-move baseline instead of treating non-empty output as failure. Worker spec Refactory Workflow step 8 and reviewer spec reflect this. Treat only *new* errors introduced by the move as merge-blocking. | Lead integrator |
| 2026-04-24 | Phase 4 batch 1 closed: `NBB-208B` at `9e7fe6a`, `NBB-401` at `5bbf9d5`, `NBB-704A` at `d102fd4`. Three documentation-weight tickets merged in parallel (disjoint write scopes: `docs/deployment/` + comment-only pointers, `backend/app/sources/` skeleton, `backend/scripts/` + `.github/workflows/`). `NBB-402` unblocked. Movers in batch 2 onward can dispatch with the refactory namespace + stdlib-baseline fixes in place. | Lead integrator |
| 2026-04-24 | Batch-parallelism rule refinement: "disjoint write scopes" must account for refactory's transitive import-rewrite fanout, not just the `Primary write scope` field. Store-move tickets like NBB-209A/B/D/E all rewrite `api/**/*.py` routes that import the old `*Service` names; NBB-201 rewrites every auth-guard import site. Pairing two movers that both touch route files (even on disjoint symbols) risks integration-time merge conflicts. Safe mover pairs are two stores targeting fully disjoint `api/*` subtrees (e.g., 209B projects ↔ 209D brand). | Lead integrator |
| 2026-04-24 | NBB-209D merged at `9f18494`. Refactory availability fully resolved in worker sessions via `.mcp.json` at `/Users/sour4bh/dev/NoobBook/.mcp.json` (gitignored, registers refactory's `server/main.py`). NBB-209D worker applied the plain 2-op sequence (move_module + rename_symbol class) with one minimal manual fix for a local-name basename collision at `api/brand/routes.py`. Confirms the "one minimal manual fix" allowance in the ticket body is the correct escape hatch for rope edge cases. | Lead integrator |
| 2026-04-24 | NBB-209B: bounded one-ticket manual repair. After four blocked attempts, root cause isolated: `project_service` has 5 LAZY in-function imports of the singleton (at `app/__init__.py:151`, `config/brand_context_loader.py:50`, `utils/cost_tracking.py:76`, `utils/auth_middleware.py:144`, `tests/auth/test_identity_and_permissions.py:149/157/176`), where the imported name equals the source module basename. Rope's `move_module` hoists these lazy imports (breaking eager init ordering) and miswrites call sites as `app.projects.store.method()` (module-attribute instead of singleton method). This is a rope-level codemod failure, not reparable by any rename-symbol sequencing — dead-singleton removal at `project_service.py:566` did not change rope's behavior. Attempt 5 authorizes a bounded manual repair: keep the 5 sites lazy but update their path to `from app.projects.store import project_service`; restore any `app.projects.store.method()` rewrite to `project_service.method()`; consolidate the singleton into a canonical `project_service = ProjectStore()` at `projects/store.py`; `data_services/__init__.py` re-exports from the new path (no second instantiation). This exception is NOT a license for broad manual migration — future mover tickets continue to use refactory unless they hit an equivalent deterministic rope failure, in which case the same narrowly-scoped pattern applies. | Lead integrator |
| 2026-04-24 | Phase 4 batch 3 merged (`NBB-209E` @ `21b094d`, `NBB-207B` @ `76ee334`). Three pieces of operational signal captured: (1) **Rope's lazy-import handling is basename-dependent.** In NBB-209E, `mcp_connection_service.py` → `store.py` (basename changed) and rope correctly preserved both lazy imports without hoisting. In NBB-209B, rope miswrote 5 lazy imports because the singleton name `project_service` was preserved through the move. Heuristic: if a mover ticket's target basename differs from the source basename AND the singleton name is not reused verbatim in consumer code, rope's plain 2-op sequence is likely safe. When in doubt, pre-authorize the bounded manual repair as a conditional. (2) **`project_root=backend/` is load-bearing for refactory apply, not just dry-run.** NBB-209E worker's first attempt with `project_root=<worktree-root>` showed correct dry-run preview (9 affected files) but apply silently rewrote only 4 of 8 consumers. Retry with `project_root=backend/` produced correct apply. Future mover prompts MUST pin `project_root=backend/` explicitly. (3) **Preserved-failure list initial read (revised by batch 4).** `backend/tests/test_asset_registry.py` path is actually `tests/config/test_asset_registry.py` (file relocated). `tests/test_cost_tracking.py::TestCalculateCost::test_unknown_model_uses_sonnet_pricing` needs the class qualifier. See batch 4 entry below for the corrected guidance on `test_public_register_helpers_exported_from_package`. | Lead integrator |
| 2026-04-24 | Phase 4 batch 4 merged (`NBB-207C` @ `de4bf76`, `NBB-210` @ `d3457c4`). Batch 5 (NBB-501A + NBB-209A) dispatched optimistically in parallel with NBB-210 reviewer. Three signals refined: (1) **Rope heuristic, expanded from NBB-210 empirical evidence.** Target basename differing from source basename is NOT sufficient protection. `task_service.py → tasks.py` changed the basename but rope still mangled 27 sites across TWO categories: **Category A** (hoisted lazy imports to module top, breaking eager-init ordering; 14 sites) AND **Category B** (eager shim-form imports `from app.services.background_services import task_service` rewritten to `from app.background import tasks` with call sites `tasks.method()` — broken because `tasks` is module, not singleton; 13 sites). Root cause: singleton name `task_service` identical to source basename `task_service.py` AND preserved verbatim in consumer code. NBB-209B hit Category A only; NBB-210 hit both. Future mover prompts with this shape should pre-authorize BOTH Category A and Category B bounded manual repairs. (2) **Preserved-failure list CORRECTION.** `tests/config/test_asset_registry.py::test_public_register_helpers_exported_from_package` DOES fail in full-suite runs due to `backend/config.py` vs `backend/app/config/` collection shadowing when `tests/test_flask_config.py` is collected alongside `tests/config/`. It passes in scoped `tests/config/` runs. My previous "drop from deselect" note (based on narrow-scope NBB-207B reviewer check) was incorrect; NBB-207C and NBB-210 workers confirmed empirically it still needs deselect for full-suite runs. Restore it to the preserved-failure list alongside `TestCalculateCost::test_unknown_model_uses_sonnet_pricing`. (3) **`backend/.ropeproject/` untracked but not gitignored.** Every refactory apply creates this dir; workers delete it before commit or it stays untracked. Flag-for-housekeeping: add to root `.gitignore` in a later cleanup ticket. Not merge-blocking. | Lead integrator |
| 2026-04-24 | Phase 4 batch 5 merged (`NBB-501A` @ `b41a791` studio taxonomy, `NBB-209A` @ `2ef4bfc` chat/message stores). **Rope heuristic now triple-categoried (A+B+C) on a single ticket.** NBB-209A's `chat_service` rewrite hit ALL THREE categories: Cat A (hoisted lazy at cost_tracking.py:80-83), Cat B (body-rewrite to module-attribute), Cat C (shim-form eager rewrite at api/chats/routes.py 6 sites + main_chat_service.py 3 sites). Total 9 sites repaired. `message_service` separately hit Cat C only across 14 ai_agents/* + main_chat_service.py files. Refined rope-hostility predictor: when (singleton name = source basename) AND (singleton survives verbatim in consumer code) AND (lazy in-function consumers exist), expect the full A+B+C combo. Pre-authorize all three categories conditionally for any mover ticket matching this shape. | Lead integrator |
| 2026-04-25 | Phase 4 batch 6 merged (`NBB-501B` @ `ed257a5` studio item registry, `NBB-402` @ `aca375b` sources 7-row migration). **NBB-402 introduced a recovery pattern for circular-import collisions: the `__getattr__` lazy re-export shim.** `services/source_services/__init__.py` couldn't be a simple eager re-export of the new `app.sources` paths because eager imports created circular-import chains via `app.sources` → `app.api.sources/*` → back to source_services. Solution: `__getattr__` at the package level lazily resolves attributes on first access. NBB-706 owns shim removal. NBB-402 also hit Cat B (25 sites) + Cat C (6 sites); no Cat A. NBB-501B was rejected once (3 P2 prompt-ownership drift findings vs NBB-207B); the redo seeded from the prior branch + applied inline reconciliation notes on exactly 3 rows. Pattern reusable for future ticket DO_NOT_MERGE recoveries with narrow scope. | Lead integrator |
| 2026-04-24 | Phase 4 batch 7 merged (`NBB-502` @ `5654c82` docs-only studio layer map, `NBB-201` @ `6aeeffc` auth consolidation). **NBB-201 discovered a 4th rope-hostile category: Blueprint init reordering.** Rope hoists `from app.api.<bp> import routes` ABOVE `<bp>_bp = Blueprint(...)` construction in `api/**/__init__.py` files, causing circular imports at Flask startup. Affects all api sub-blueprint `__init__.py` that follow the shared pattern. Pre-authorize re-ordering (restore Blueprint() before route-module imports) in any future mover touching api/**/__init__.py. NBB-201 hit 6 such files (chats, google, prompts, messages, sources, studio). Also observed: Cat B dominated (26 decorator-rewrite sites for auth guards); Cat A and C both zero. Barrel-rewrite pattern (gut `__init__.py` re-exports, route callers to new paths in same commit) successful. Test-ordering quirk surfaced: auth tests leave Flask/env state affecting `test_unregistered_route_returns_404` when auth runs before smoke; full-suite alphabetical ordering avoids it. Not merge-blocking but worth future cleanup. | Lead integrator |
| 2026-04-25 | Phase 4/5 batch 8 merged (`NBB-202A` @ `872d18a` fail-closed permissions, `NBB-503` @ `4980de5` studio pilot — design/website). Three operational signals: (1) **Stream-timeout recovery pattern.** NBB-503 worker's stream timed out mid-pilot after completing all moves but before committing. Dispatcher committed the worker's uncommitted state on its branch as recovery. Subsequent recovery worker(s) cherry-picked + applied narrow fixes. Multi-stage recovery preserved ~951 lines of carved code that would otherwise have been lost. Pattern: dispatcher git-commits-on-behalf-of-dead-worker is acceptable as a preservation step; downstream worker takes ownership of the revised result. (2) **LAYER_MAP entrypoint-method lock requires renaming the METHOD, not just the class.** First NBB-503 recovery renamed `WebsiteToolExecutor` → `WebsiteDispatcher` (class) but kept `execute_tool(...)` as the method entrypoint. Reviewer rejected on P1 — LAYER_MAP.md:27/63 polices the entrypoint-method name. Recovery-2 renamed method to `dispatch(...)`. Future studio migration tickets (NBB-504-507) must rename method too, not just class. (3) **NBB-202A intentional asymmetry (preserve in NBB-705A drain):** `get_user_permissions()` returns DEFAULT_PERMISSIONS on DB error so admin UI can populate toggles; `user_has_permission()` re-queries and denies in auth-required mode. Removing this asymmetry would weaken the security property; NBB-705A must preserve it. | Lead integrator |
| 2026-04-25 | Phase 4/5 batch 9 partial close (`NBB-209C` @ `2302823` auth user/password stores). **Rope-hostility-zero result via factory indirection.** Despite matching all prior rope-hostile preconditions on paper (singleton name matches source basename `user_service` ≈ `user_service.py`; consumer code exists), ZERO manual repairs were needed. Root cause: the singleton is exclusively accessed through `get_user_service()` factory function, not bare `user_service` attribute. Rope correctly rewrote factory call sites without mangling lazy imports (cost_tracking.py :300/:357) or triggering shim-form collapse. Heuristic refinement: **factory-gated singletons are rope-safe** even when basename collides. Future mover tickets should ask early "does the singleton have a factory?" — if yes, Cat A/B/C pre-authorization is prudent but typically unused. Also: refactory `move_module` correctly handles basename change via 2-op split (same-basename relocate + in-dir rename); intermediate path never commits; move-plan.csv records both ops. Unblocked NBB-705A. Batch 9 workers 504/505/506 remain in flight; batch 10 can plan NBB-507 + NBB-202B + 602+705C once studio parallelism lands. | Lead integrator |

## Done Criteria for the Sprint

The sprint is complete when:

- `NBB-706` is merged.
- `docs/tickets/dag.py --check` passes.
- `move-plan.csv` accounts for every mechanical move that landed.
- No forwarding-only compatibility modules remain without documented reason.
- Final backend architecture docs describe the migrated truth.
- `DEFERRED.md` still names all known out-of-scope work and guardrails.
