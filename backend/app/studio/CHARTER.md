# `studio/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which storage buckets, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, bucket, or JSONB field below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` and `backend/supabase/STORAGE_CONTRACTS.md` to spot-check.

**Migration source:** legacy studio services were drained from `backend/app/services/studio_services/` into this domain across `NBB-501A` through `NBB-809`.

## Tables owned by `studio/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `studio_signals` | `backend/supabase/migrations/00001_initial_schema.sql`, RLS in `00003_rls_policies.sql` | Hosted: RLS via `studio_signals.chat_id -> chats.project_id -> projects.user_id`. Self-hosted: backend guard on route entry. | `studio_item` CHECK constraint enumerates legacy taxonomy names; NBB-501A finalizes the canonical list. Any rename must land as a migration + constraint update in the NBB-501A/NBB-501B batch. |
| `studio_jobs` | `00009_studio_jobs.sql` | **No RLS.** Backend guard only. Route entry runs `has_project_access`; the job row carries `project_id` and rows are filtered by project on read. | NBB-502 should decide whether to add RLS when the job/tool/run layer is locked. Until then treat the absence of RLS as a documented gap, not a bug. |

## Storage buckets owned by `studio/`

| Bucket | Object path (runtime) | Serving route | Notes |
|---|---|---|---|
| `studio-outputs` | `{user_id}/{project_id}/studio/{job_type}/{job_id}/{filename}` and `{user_id}/{project_id}/ai-images/{filename}` | `GET /api/v1/projects/{project_id}/studio/<category>/...` routes in `backend/app/api/studio/` return signed URLs or stream bytes through backend routes; CSV analysis images are served at `/api/v1/projects/{project_id}/ai-images/{filename}` | Runtime builders and storage RLS agree after `00021_storage_owner_paths.sql`. |

Path builder: `backend/app/providers/supabase/storage.py::_build_studio_path`. Do not introduce new path builders for this bucket elsewhere.

## JSONB contracts owned here (shape lives in NBB-205)

| Column | Table | Defined in | Purpose |
|---|---|---|---|
| `studio_signals.direction` | `studio_signals` | 00001 | AI-provided context and instructions for generation. |
| `studio_signals.source_ids` | `studio_signals` | 00001 | `UUID[]` of source rows to use for generation. |
| `studio_jobs.job_data` | `studio_jobs` | 00009 | Type-specific fields (audio_path, videos[], slides[], etc.). Shape contract owner: NBB-205. |

## Access guard of record

- Entry guard: `@before_request` enforcement in `backend/app/__init__.py` calls `project_service.has_project_access(project_id, user_id)` for every `/api/v1/projects/{id}/studio/...` route.
- RLS defence-in-depth (hosted, `studio_signals`): `00003_rls_policies.sql` uses chat -> project -> user ownership subqueries. A missed guard in a signal route is still blocked at the DB layer in hosted deployments.
- `studio_jobs` has no RLS in either deployment. Cross-user protection depends entirely on the route-level project guard. Keep every studio-jobs read/write path behind a project-scoped route until NBB-502 decides the RLS model.
- Signed URL issuance and byte streaming for `studio-outputs` happens inside project-scoped routes. Do not expose a URL generator or streaming route that does not first run the project guard.

## Data-move pre-flight (NBB-502, NBB-503, NBB-704B)

1. Preserve the `studio-outputs` object-path contract from `00021_storage_owner_paths.sql`; any path change needs a migration and a storage-object backfill.
2. When NBB-501B maps studio items, every new category route must be added to the serving-route table in `STORAGE_CONTRACTS.md`.
3. `studio_jobs` background integration is owned by `NBB-210` / `background/`; do not duplicate job lifecycle state inside studio item code.
4. If NBB-502 adds RLS to `studio_jobs`, update this file and `OWNERS.md` in the same PR.

## Cross-reference

- Import/dependency charter: `backend/app/studio/__init__.py`.
- Taxonomy (categories/items): `backend/app/studio/TAXONOMY.md` (NBB-501A).
- Registry (per-item current vs target): `backend/app/studio/REGISTRY.md` (NBB-501B).
- Per-item layer map (five-file shape + executable naming rule + contract links): `backend/app/studio/LAYER_MAP.md` (NBB-502).
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage bucket and object-path contracts: `backend/supabase/STORAGE_CONTRACTS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
