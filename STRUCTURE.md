# NoobBook Repository Structure

This file is the repo-root structure guide. It states the direction of the ongoing structure migration and tells contributors and agents where new code belongs. It overrides older placement guidance in `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and `REFACTORING.md` during the migration.

Ticket tracking lives in `docs/tickets/`. Epic `NBB-001` (`docs/tickets/epics/NBB-001.md`) is the source of truth for the migration plan. This file is the human-readable rules summary that applies every day while the migration is in progress.

## Direction

The migration replaces the former mechanism-first backend layout (`services/`, `utils/`, `ai_agents/`, `ai_services/`, `tool_executors/`, `services/tools/`, `data/prompts/`) with a **domain-first** layout. New behavior lives under the domain that owns it rather than under a bucket named after the technical mechanism it uses.

## Canonical Backend Roots (NBB-104)

The backend root list is finalized. Every backend file belongs under exactly one of these roots. No new backend root may be created without amending this list through a follow-up ticket.

| Root | Purpose |
|---|---|
| `backend/app/api/` | Transport adapters only: parse HTTP, run guards, call domain public surfaces, format responses. |
| `backend/app/auth/` | Identity, route/service guards, permission policy, user identity store. |
| `backend/app/projects/` | Project domain behavior and project store. |
| `backend/app/chat/` | Chat loop, streaming, memory invocation, chat persistence coordination. |
| `backend/app/sources/` | Source ingestion, search, citation, extraction, indexing, and analysis. |
| `backend/app/studio/` | Studio generation items and studio job/tool/run behavior. |
| `backend/app/brand/` | Brand config and brand asset ownership. |
| `backend/app/settings/` | App/user settings and API-key UI backend. |
| `backend/app/config/` | Runtime config, provider/model/prompt/tool loaders, and registered asset paths. |
| `backend/app/connectors/` | Product-level configured external capabilities, user/project connection stores, permission-gated tool surfaces. |
| `backend/app/providers/` | Low-level external API clients, SDK wrappers, auth primitives, storage adapters, and runtime IO adapters. |
| `backend/app/background/` | Task lifecycle, cancellation, active-task status, and execution-log ownership. |
| `backend/app/base/` | Cross-domain primitives with 3+ domain consumers and no better owner. Current members: runtime paths and logging setup. |

Each root's `__init__.py` carries the full charter (owner scope, allowed import direction, migration sources). Read the charter before adding a file to a root.

Legacy roots are not approved destinations. `backend/app/services/` has been
drained and must remain empty of tracked files after NBB-811. `backend/app/utils/`
and `backend/data/prompts/` are retired by NBB-812; their surviving behavior and
assets now live under canonical roots.

## Base and Shared Charters (NBB-104)

| Directory family | Charter |
|---|---|
| `backend/app/base/` | Reserved for truly cross-domain primitives with 3+ domain consumers and no better owner. `base.paths` and `base.logging` are the NBB-812 homes for the final app-wide utility residents; new files still require a PR note explaining why no domain owns them. |
| `backend/app/<domain>/shared/` | Allowed only after that domain has 3+ concrete slices using the same behavior. The shared code must name the boundary it serves, for example `studio/shared/` or `sources/analysis/shared/`. |
| Preemptive `shared/` directories | Forbidden. A directory cannot exist only to reserve a future convenience bucket. |
| Generic helpers in `base/` or `shared/` | Forbidden. Rehome to the owning domain, provider/client boundary, or connector capability. |

## Dependency Direction (NBB-104)

Backend imports flow in one direction:

```text
api/ -> domain public surfaces -> connector public surfaces -> provider clients
```

- `api/` route modules may import domain public surfaces, not domain internals.
- Domains may depend on other domains' public surfaces only when the ticket body calls for it. Domains must not reach into another domain's internals.
- Connectors wrap providers into configured product capabilities and expose tool surfaces to domains.
- Domains may depend on `providers/` directly only for provider-neutral runtime primitives (for example HTTP clients, storage adapters, Claude API primitives). Product-specific integrations must pass through `connectors/`.
- `providers/` does not import from `api/`, domains, or `connectors/`.
- `base/` does not import from `api/`, any domain, `connectors/`, or `providers/`.

Rich import-boundary enforcement is owned by `NBB-704A` and `NBB-704B`.

### Providers/Connectors boundary (NBB-206)

`providers/` owns raw SDK clients, auth primitives, and runtime IO adapters; `connectors/<name>/` owns product-configured capabilities with user/project state and permission-gated tool schemas. See `backend/app/providers/CHARTER.md` and `backend/app/connectors/CHARTER.md` for the full inventory, the validator/reload cross-reference to `NBB-208A`, and the downstream move tickets (`NBB-705C`, `NBB-207C`, `NBB-209E`, `NBB-202B`).

`platform/files/` and `providers/files/` are explicitly rejected as default homes. File-format ownership follows `NBB-401` (`docs/tickets/epics/NBB-004.md#nbb-401`); it is never a provider or connector concern.

## Frozen Destinations

The following paths are frozen. New files must not be added to them unless they are explicitly allowlisted temporary shims justified by an active ticket:

- `backend/app/services/`
- `backend/app/utils/`
- `backend/app/services/ai_agents/`
- `backend/app/services/ai_services/`
- `backend/app/services/tool_executors/`
- `backend/app/services/tools/`
- `backend/app/services/studio_services/jobs/` (directory removed by `NBB-802`; do not recreate)
- `backend/app/services/studio_services/studio_processing/` (directory removed by `NBB-802`; do not recreate)
- `backend/data/prompts/`
- `frontend/src/components/hooks/` (directory removed by `NBB-602`; entry retained for the legacy-files guardrail)

These paths are frozen no-return locations. Some remain only as historical
migration sources or guardrail entries; `backend/app/services/`,
`backend/app/utils/`, and `backend/data/prompts/` must not regain tracked files.
`app.services.*` and `app.utils.*` imports are forbidden. Do not add new files
to these paths and do not describe them as the preferred home for new work.

`NBB-103` enforces the frozen list in CI. `NBB-811` adds the final services
no-return gate. `NBB-812` extends the gate to `backend/app/utils/`,
`backend/data/prompts/`, and `app.utils.*` imports.

## Allowed Destinations

New backend behavior lands under its domain root from the Canonical Backend Roots
table above. Historical migration sources named in root charters are not live
destinations; read the charter before adding or moving a file.

External clients and SDK wrappers follow the providers/connectors split defined by `NBB-206`. Background task behavior lives under the background owner defined by `NBB-210`. Prompt JSON and tool JSON live in domain-owned directories and resolve through the asset registry; `backend/data/prompts/` and `backend/app/services/tools/` are retired.

## Placement Checklist (canonical)

Reviewers and authors run this checklist for every new file. If any row fails, the file is in the wrong place.

1. **Domain ownership is identifiable.** The file has exactly one domain owner (chat, sources, studio, auth, projects, brand, settings, background, connectors, providers). "Utilities" is not a domain.
2. **Not in a frozen destination.** The target path is not inside any directory in the frozen list above, and is not a new file directly under `backend/app/services/` or `backend/app/utils/`.
3. **Path reflects the owning concept, not the mechanism.** Name the directory after what the code is *about* (`chat/`, `sources/ingestion/`, `studio/<category>/`), not after how it is implemented (`agents/`, `ai_services/`, `executors/`).
4. **External edge respected.** Low-level external clients sit under `providers/`; product-configured capabilities sit under `connectors/`; domain behavior does not reach into another domain's internals.
5. **Shared or base boundaries are earned.** New `base/` or `<domain>/shared/` files cite the `NBB-104` charter rule (3+ concrete consumers, no better owner). Preemptive `shared/` directories are not created.
6. **Prompt/tool JSON follows owning domains.** New prompt JSON is not added under frozen `backend/data/prompts/`; new tool JSON is not added under retired `backend/app/services/tools/`. Tool JSON now lives in domain-owned `tools/` directories and resolves through the asset registry.
7. **Frontend features land under owning subtrees.** New feature-specific React code lives under its feature subtree (for example `frontend/src/components/chat/`, `frontend/src/components/sources/`, `frontend/src/components/studio/`), not in shell buckets such as `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/lib/`, or `frontend/src/contexts/` whose meaning `NBB-105` tightens. The legacy `frontend/src/components/hooks/` directory was removed by `NBB-602`; it remains in the frozen list above only as a CI guardrail entry.
8. **Refactory used for moves.** If this file is reached by moving or renaming an existing module, the movement ticket uses the refactory MCP plugin and records the operation in `docs/tickets/move-plan.csv` per `docs/tickets/README.md`.

If the answer to any row is "I am not sure," stop and check the owning ticket in `docs/tickets/epics/*.md` instead of guessing a path.

## Status of Older Placement Guidance

The `AI Service Standard Pattern` section in `AGENTS.md` and `CLAUDE.md`
documents a useful Claude-API integration pattern. Its step list (config
loading, path management, API call, response parsing) is accurate project
knowledge. Any legacy bucket names it uses (`ai_services/`, `ai_agents/`,
`tool_executors/`) are historical source names, not current homes for new work.

`REFACTORING.md` was written against the legacy mechanism-first layout. Its prescriptive wording ("put X in `ai_services/`", "move tool handlers to `tool_executors/`") is superseded by this file. Its tables of past refactors are historical record and remain useful.

After the services drain, both sets of docs should be read as: *structure rules
live in `STRUCTURE.md`; legacy mechanism paths are historical context only.*
