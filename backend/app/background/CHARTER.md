# `background/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, column, or claim below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` to spot-check.

**Migration source (NBB-210):** background task coordination currently lives under `backend/app/services/background_services/`; `NBB-210` consolidates ownership here.

## Tables owned by `background/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `background_tasks` | `backend/supabase/migrations/00001_initial_schema.sql`, RLS in `00003_rls_policies.sql`, `started_at` added in `00012_background_tasks_started_at.sql` | Hosted: polymorphic RLS — for `target_type='source'` uses sources -> projects subquery; for `target_type='studio_signal'` uses studio_signals -> chats -> projects; for `target_type='chat'` uses chats -> projects. Self-hosted: backend guard on the route entry that creates or polls the task. | `target_type` CHECK enumerates `source | studio_signal | chat`. Extending it requires migration + RLS policy update in the same ticket. |

## Columns owned here

| Column | Defined in | Purpose |
|---|---|---|
| `background_tasks.target_id`, `target_type`, `task_type` | 00001 | Polymorphic task target. RLS depends on the `target_type` enum to pick the right ownership subquery. |
| `background_tasks.status` | 00001 | `pending | running | completed | failed | cancelled`. |
| `background_tasks.progress` | 00001 | 0-100 integer. |
| `background_tasks.started_at` | 00012 | Populated when the worker picks the task up. |

## Access guard of record

- Entry guard: every route that creates or polls a background task is project-scoped (`/api/v1/projects/{id}/...`), so `@before_request` enforcement in `backend/app/__init__.py` runs `project_service.has_project_access` first.
- RLS defence-in-depth (hosted): polymorphic policies in `00003_rls_policies.sql` walk `target_id` through the owning resource (source / studio_signal / chat) back to the project. Any new `target_type` value must extend each of the four policies (SELECT/INSERT/UPDATE/DELETE) to add the new subquery branch.
- Self-hosted mode has no RLS; the project guard is the only barrier.

## Data-move pre-flight (NBB-210, NBB-703)

1. When NBB-210 consolidates lifecycle under this root, preserve the polymorphic RLS walk. Do not introduce a helper that creates a `background_tasks` row outside a project-scoped route.
2. Adding a new `target_type` (for example `brand_asset` or a connector target) requires a migration that updates the CHECK constraint **and** the four RLS policies in the same PR. Update this file's "Notes" row in the same PR.
3. If NBB-210 moves active-task status tracking out of Redis/local memory into a new column or table, add the column here and to `OWNERS.md`.
4. NBB-703 will add job background status tests against the serving routes; this charter is the inventory those tests assert against.

## Cross-reference

- Import/dependency charter: `backend/app/background/__init__.py`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
