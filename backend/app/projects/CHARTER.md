# `projects/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, column, or JSONB field below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` to spot-check.

**Migration source (NBB-209B):** project persistence formerly lived in `backend/app/services/data_services/project_service.py`; `NBB-209B` moved it under this root and `NBB-802` removed the dead residue.

## Tables owned by `projects/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `projects` | `backend/supabase/migrations/00001_initial_schema.sql`, `00003_rls_policies.sql`, `00023_workspace_membership.sql` | Hosted: RLS checks explicit `project_members` membership through `user_has_project_access`. Self-hosted: backend guard `project_service.has_project_access` checks explicit `project_members` roles. | Project row belongs to a workspace through `workspace_id`, but workspace membership alone is not project access. |
| `project_members` | `backend/supabase/migrations/00006_user_roles.sql`, rewritten by `00023_workspace_membership.sql` | Hosted: RLS lets project members view membership and project owners manage membership. Backend guard/API checks augment in self-hosted mode. | Private project access roles are `owner`, `editor`, and `viewer`. |

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
- Runtime guard: `backend/app/projects/store.py::has_project_access` and project CRUD use explicit `project_members` roles. Workspace membership alone does not satisfy project reads or writes.
- RLS defence-in-depth (hosted): `migrations/00023_workspace_membership.sql` gates `projects` and project-owned child tables through private project membership.

## Data-move pre-flight (any `NBB-209*` ticket touching project data)

1. Confirm the move does not bypass `has_project_access`. If a service call needs to skip the guard, document it here and in the ticket body.
2. If the move adds a new column or JSONB field, add it to the table above and cross-link the migration.
3. If the move changes the ownership query, update `backend/supabase/migrations/OWNERS.md` and the access smoke checklist.

## Cross-reference

- Import/dependency charter: `backend/app/projects/__init__.py`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage contracts (not applicable to `projects/`, but relevant when `projects/` exposes project-scoped resources): `backend/supabase/STORAGE_CONTRACTS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
