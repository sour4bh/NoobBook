# `projects/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, column, or JSONB field below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` to spot-check.

**Migration source (NBB-209B):** project persistence currently lives in `backend/app/services/data_services/project_service.py`; `NBB-209B` moves it under this root.

## Tables owned by `projects/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `projects` | `backend/supabase/migrations/00001_initial_schema.sql`, `00003_rls_policies.sql` | Hosted: RLS `user_id = auth.uid()` for select/insert/update/delete. Self-hosted: backend guard `project_service.has_project_access`. Both layers coexist in hosted mode. | Project row is the ownership root for every project-scoped table. |
| `project_members` | `backend/supabase/migrations/00006_user_roles.sql` | RLS on role-gated actions (owner/admin + `can_invite` for inserts). Backend guard augments in self-hosted mode. | Multi-user collaboration; `has_project_access` must be amended if collaboration is re-enabled in self-hosted. |

Auxiliary tables defined elsewhere but keyed to `project_id`:

- `sources`, `chunks` -> owned by `sources/` (see `backend/app/sources/CHARTER.md`).
- `chats`, `messages` -> owned by `chat/` (see `backend/app/chat/CHARTER.md`).
- `studio_signals`, `studio_jobs` -> owned by `studio/` (see `backend/app/studio/CHARTER.md`).
- `background_tasks` -> owned by `background/` (see `backend/app/background/CHARTER.md`).

`projects/` does not expose internal readers for those tables; other domains read them through their own public surfaces.

## JSONB contracts owned here (shape lives in NBB-205)

| Column | Defined in | Purpose |
|---|---|---|
| `projects.memory` | 00001 | Project-specific memory string merged into the chat system prompt. |
| `projects.costs` | 00001 | Per-project cost tracking mirrored in `chats.costs` (00018). Updated via `backend/app/providers/anthropic/cost.py`. |

## Access guard of record

- Entry guard: `@before_request` enforcement in `backend/app/__init__.py` calls `project_service.has_project_access(project_id, user_id)` for every `/api/v1/projects/{id}/...` route.
- Ownership query: `backend/app/services/data_services/project_service.py::has_project_access` performs a bare `id=? AND user_id=?` lookup against the `projects` table. It does **not** currently consult `project_members`; extend this (or call `user_has_project_access()` SQL helper from migration 00006) when multi-user collaboration is re-enabled.
- RLS defence-in-depth (hosted): `migrations/00003_rls_policies.sql` gates `projects` by `auth.uid() = user_id`.

## Data-move pre-flight (any `NBB-209*` ticket touching project data)

1. Confirm the move does not bypass `has_project_access`. If a service call needs to skip the guard, document it here and in the ticket body.
2. If the move adds a new column or JSONB field, add it to the table above and cross-link the migration.
3. If the move changes the ownership query, update `backend/supabase/migrations/OWNERS.md` and the access smoke checklist.

## Cross-reference

- Import/dependency charter: `backend/app/projects/__init__.py`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage contracts (not applicable to `projects/`, but relevant when `projects/` exposes project-scoped resources): `backend/supabase/STORAGE_CONTRACTS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
