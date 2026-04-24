# NoobBook Repository Structure

This file is the repo-root structure guide. It states the direction of the ongoing structure migration and tells contributors and agents where new code belongs. It overrides older placement guidance in `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and `REFACTORING.md` during the migration.

Ticket tracking lives in `docs/tickets/`. Epic `NBB-001` (`docs/tickets/epics/NBB-001.md`) is the source of truth for the migration plan. This file is the human-readable rules summary that applies every day while the migration is in progress.

## Direction

The migration replaces a mechanism-first backend layout (`services/`, `utils/`, `ai_agents/`, `ai_services/`, `tool_executors/`, `services/tools/`, `data/prompts/`) with a **domain-first** layout. New behavior should live under the domain that owns it (chat, sources, studio, auth, projects, brand, settings, background, connectors, providers, api) rather than under a bucket named after the technical mechanism it uses.

The canonical backend root list (auth, projects, chat, sources, studio, brand, settings, connectors, providers, background, api, base) is finalized by ticket `NBB-104`. Until `NBB-104` publishes that decision, new backend work should:

- Not default to any frozen destination in the list below.
- Land under the closest obvious domain if one exists in the tree today, or wait on `NBB-104` if placement is genuinely unclear.
- Never land in a frozen destination.

## Frozen Destinations

The following paths are frozen. New files must not be added to them unless they are explicitly allowlisted temporary shims justified by an active ticket:

- `backend/app/services/`
- `backend/app/utils/`
- `backend/app/services/ai_agents/`
- `backend/app/services/ai_services/`
- `backend/app/services/tool_executors/`
- `backend/app/services/tools/`
- `backend/app/services/studio_services/jobs/`
- `backend/app/services/studio_services/studio_processing/`
- `backend/data/prompts/`
- `frontend/src/components/hooks/`

These paths still contain code today. Treat them as **legacy/migration sources**: you may read from them, import from them, and drain from them as ownership moves. Do not add new files to them and do not describe them as the preferred home for new work.

`NBB-103` will enforce this list in CI. `NBB-705A` through `NBB-705E` and `NBB-706` drain or delete what remains.

## Allowed Destinations (interim rule)

During the migration, new backend work should land under the owning domain subtree that already exists, or wait on the `NBB-104` charter if the domain does not exist yet:

- Domain behavior: the domain directory (for example `backend/app/services/chat/`, `backend/app/services/sources/`, `backend/app/services/studio/`, `backend/app/services/auth/`, `backend/app/services/projects/`, `backend/app/services/brand/`, `backend/app/services/app_settings/`).
- External clients and SDK wrappers: under the providers/connectors split defined by `NBB-206`.
- Background task behavior: under the background owner defined by `NBB-210`.
- Prompt JSON and tool JSON: wait for `NBB-207A` loader support; until then do not move existing JSON assets.

`NBB-104` may rename or re-root these subtrees. Agents must not pre-empt that decision by inventing new root names.

## Placement Checklist (canonical)

Reviewers and authors run this checklist for every new file. If any row fails, the file is in the wrong place.

1. **Domain ownership is identifiable.** The file has exactly one domain owner (chat, sources, studio, auth, projects, brand, settings, background, connectors, providers). "Utilities" is not a domain.
2. **Not in a frozen destination.** The target path is not inside any directory in the frozen list above, and is not a new file directly under `backend/app/services/` or `backend/app/utils/`.
3. **Path reflects the owning concept, not the mechanism.** Name the directory after what the code is *about* (`chat/`, `sources/ingestion/`, `studio/<category>/`), not after how it is implemented (`agents/`, `ai_services/`, `executors/`).
4. **External edge respected.** Low-level external clients sit under `providers/`; product-configured capabilities sit under `connectors/`; domain behavior does not reach into another domain's internals.
5. **Shared or base boundaries are earned.** New `base/` or `<domain>/shared/` files cite the `NBB-104` charter rule (3+ concrete consumers, no better owner). Preemptive `shared/` directories are not created.
6. **Prompt/tool JSON deferred to `NBB-207A`.** New prompt JSON or tool JSON is not added under `backend/data/prompts/` or `backend/app/services/tools/` until `NBB-207A` loader shims land; once they do, ownership follows `NBB-207B` (prompts) and `NBB-207C` (tools).
7. **Frontend features land under owning subtrees.** New feature-specific React code lives under its feature subtree, not in `frontend/src/components/hooks/` or other root-level buckets whose meaning `NBB-105` tightens.
8. **Refactory used for moves.** If this file is reached by moving or renaming an existing module, the movement ticket uses the refactory MCP plugin and records the operation in `docs/tickets/move-plan.csv` per `docs/tickets/README.md`.

If the answer to any row is "I am not sure," stop and check the owning ticket in `docs/tickets/epics/*.md` instead of guessing a path.

## Status of Older Placement Guidance

The `AI Service Standard Pattern` section in `AGENTS.md` and `CLAUDE.md` documents a useful Claude-API integration pattern. Its step list (config loading, path management, API call, response parsing) is accurate project knowledge. The bucket names it uses (`ai_services/`, `ai_agents/`, `tool_executors/`) describe where those modules currently live during migration, not a preferred home for new work.

`REFACTORING.md` was written against the legacy mechanism-first layout. Its prescriptive wording ("put X in `ai_services/`", "move tool handlers to `tool_executors/`") is superseded by this file. Its tables of past refactors are historical record and remain useful.

Until the migration completes and `NBB-706` removes leftovers, both sets of docs should be read as: *structure rules live in `STRUCTURE.md`; everything else is context.*
