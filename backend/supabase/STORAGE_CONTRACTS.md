# Supabase storage buckets and object-path contracts

**Owner (NBB-204):** Backend data-contracts lane. Owns the bucket inventory, object-path conventions, the serving-route map, and the guard-of-record for each bucket. Domain-owned storage clients (`sources/`, `studio/`, `brand/`) must consult this file before renaming an object path or adding a new bucket.

**Validation approach:** every entry below must point at (a) the defining migration, (b) the path builder in runtime code, and (c) the route that serves the object or redirects to a signed URL. Pull requests that touch any of those three must cite this file in the review description.

**Cross-reference:** table contracts and RLS status live in `migrations/OWNERS.md`. Cross-user smoke checklist lives in `../../docs/tickets/checklists/data_access_smoke.md`.

## Bucket inventory

| Bucket | Public? | Size limit | Defined in | Storage policy (hosted) | Storage policy (self-hosted) | Path builder | Owning domain |
|---|---|---|---|---|---|---|---|
| `raw-files` | false | 100 MB | `migrations/00002_storage_buckets.sql` | `auth.uid()::text == (storage.foldername(name))[1]` (per-op) | `Allow all on raw-files` (init.sql) | `_build_path(project_id, source_id, filename)` in `backend/app/providers/supabase/storage.py` | `sources/` |
| `processed-files` | false | 100 MB | `migrations/00002_storage_buckets.sql` | Same `auth.uid()` shape as `raw-files` | `Allow all on processed-files` | `_build_path(project_id, source_id, filename)` | `sources/` |
| `chunks` | false | 10 MB | `migrations/00002_storage_buckets.sql` | Same `auth.uid()` shape | `Allow all on chunks` | `_build_path(project_id, source_id, chunk_id)` (same helper, called with chunk filenames) | `sources/` (indexing slice) |
| `studio-outputs` | false | 500 MB | `migrations/00002_storage_buckets.sql` | Same `auth.uid()` shape | `Allow all on studio-outputs` | `_build_studio_path(project_id, job_type, job_id, filename)` | `studio/` |
| `brand-assets` | false | n/a (no limit declared in migration; 00007 + 00010 own the table-side path) | `migrations/00007_brand_assets.sql` + path update in `00010_brand_to_user_level.sql` | `Allow all on brand-assets` (single-user); hosted deployments rely on the user-scoped table RLS plus the first folder being `user_id` | `Allow all on brand-assets` | `_build_brand_path(user_id, asset_id, filename)` | `brand/` |

## Object-path contracts

| Bucket | Object path (today) | Migration generator | Runtime builder | Notes |
|---|---|---|---|---|
| `raw-files` | `{project_id}/{source_id}/{filename}` | `generate_raw_file_path(user_id, project_id, source_id, filename)` **defines** `{user_id}/{project_id}/{source_id}/{filename}` in 00002 | `_build_path(project_id, source_id, filename)` | See "Known inconsistency — enforcement in practice" below. |
| `processed-files` | `{project_id}/{source_id}/{source_id}.txt` | `generate_processed_file_path` in 00002 defines `{user_id}/{project_id}/{source_id}/{filename}` | `_build_path(project_id, source_id, filename)` | Same inconsistency as `raw-files`. |
| `chunks` | `{project_id}/{source_id}/{chunk_id}.txt` | No migration helper; path convention is code-only | `_build_path(project_id, source_id, chunk_id)` | Same inconsistency as `raw-files`. |
| `studio-outputs` | `{project_id}/{job_type}/{job_id}/{filename}` | `generate_studio_output_path(user_id, project_id, studio_signal_id, filename)` defines `{user_id}/{project_id}/studio/{studio_signal_id}/{filename}` in 00002 | `_build_studio_path(project_id, job_type, job_id, filename)` | Same inconsistency. Additionally, the code uses `job_type` and `job_id` while the SQL helper uses `studio_signal_id` — NBB-502/NBB-503 should reconcile when studio job semantics are locked. |
| `brand-assets` | `{user_id}/brand/{asset_id}/{filename}` | `generate_brand_asset_path(user_id, asset_id, filename)` in 00010 matches | `_build_brand_path(user_id, asset_id, filename)` | Consistent. |

## Serving-route and guard map

| Bucket | Read surface | Write surface | Guard of record |
|---|---|---|---|
| `raw-files` | `GET /api/v1/projects/{project_id}/sources/{source_id}/download` (`backend/app/api/sources/routes.py` `download_source`) redirects to signed URL from `storage_service.get_raw_file_url` | `POST /api/v1/projects/{project_id}/sources` (`upload_source` in `backend/app/api/sources/routes.py`) | `@before_request` enforce in `backend/app/__init__.py` -> `project_service.has_project_access(project_id, user_id)`. Hosted mode adds RLS defence-in-depth via `sources` policies (which gate the DB metadata read before a path is ever looked up). |
| `processed-files` | Internal only (read during ingestion/search in `backend/app/sources/` and chat context loaders) | Ingestion pipeline writes via `storage_service.upload_processed_file` | Project guard + RLS on the `sources` row the path is derived from. |
| `chunks` | Internal only (read by `source_search_executor` and the chunk citation route below) | Ingestion pipeline writes via `storage_service.upload_chunk` | Project guard + RLS on `chunks`. Citation lookup path: `GET /api/v1/projects/{project_id}/citations/{chunk_id}` (see `backend/app/api/sources/`). |
| `studio-outputs` | `GET /api/v1/projects/{project_id}/studio/{category}/...` category routes in `backend/app/api/studio/` generate signed URLs via `storage_service.get_studio_signed_url`/`get_studio_public_url` | Studio generators write via `storage_service.upload_studio_file` / `upload_studio_binary` | Project guard. `studio_jobs` has no RLS (see `migrations/OWNERS.md`); studio signed-URL issuance depends on the route-level project guard to reject cross-user reads. |
| `brand-assets` | `GET /api/v1/brand/...` routes in `backend/app/api/brand/routes.py` issue signed URLs via `storage_service.get_brand_asset_url` | `POST /api/v1/brand/...` upload surfaces | Hosted: `brand_assets` RLS (`user_id = auth.uid()`) is the primary guard. Self-hosted: backend auth + user-scoped path. |

## Known inconsistency — enforcement in practice

The migrations and the runtime code disagree about whether `user_id` prefixes the object path for the four source/studio buckets. This is a load-bearing inventory finding and intentionally not fixed by NBB-204.

Facts:

1. `migrations/00002_storage_buckets.sql` defines four storage policies of the shape
   ```sql
   auth.uid()::text = (storage.foldername(name))[1]
   ```
   which require the first folder of every object name to be the authenticated user's id.
2. `migrations/00002_storage_buckets.sql` also declares `generate_raw_file_path`, `generate_processed_file_path`, and `generate_studio_output_path` with a leading `{user_id}/` segment. These are helper functions and are **not** called by the Python runtime.
3. `backend/app/providers/supabase/storage.py` builds actual object paths without a leading `{user_id}/` segment:
   - `_build_path(project_id, source_id, filename)` -> `{project_id}/{source_id}/{filename}` for `raw-files`, `processed-files`, and `chunks`.
   - `_build_studio_path(project_id, job_type, job_id, filename)` -> `{project_id}/{job_type}/{job_id}/{filename}` for `studio-outputs`.
   - `_build_brand_path(user_id, asset_id, filename)` -> `{user_id}/brand/{asset_id}/{filename}` — the only runtime path that satisfies the `auth.uid()::text == folder[1]` rule.
4. `backend/supabase/init.sql` (self-hosted Docker bootstrap) replaces the restrictive `storage.objects` policies with `Allow all on <bucket>` for every bucket. In that deployment mode the mismatch is invisible because the storage RLS is effectively off.
5. The Supabase client (`backend/app/providers/supabase/client.py`) is built with `SUPABASE_SERVICE_KEY` when set, falling back to `SUPABASE_ANON_KEY`. When the service key is used, storage writes go through the backend with RLS bypassed; the `@before_request` project guard in `backend/app/__init__.py` is what prevents cross-user access today.

Consequence for this ticket's inventory:

- The **guard of record** for `raw-files`, `processed-files`, `chunks`, and `studio-outputs` is the backend project guard (`project_service.has_project_access`). Storage RLS on those buckets is **advisory in hosted mode and disabled in self-hosted mode**.
- `brand-assets` is the only bucket whose runtime path satisfies the `auth.uid()` first-folder rule. It is the only bucket where storage RLS is primary.

Action owners for a future fix (out of scope here):

- Reconcile the bucket RLS policies with the runtime path (either add the `{user_id}/` prefix in the path builders or change the policies to use a project-ownership subquery). This requires a migration + a data backfill and must be scheduled as its own ticket, not this one.
- `NBB-502`/`NBB-503` should use this reconciliation window to align `studio-outputs` paths with the studio job/tool/run layer map.

## Pre-move checklist for data-store moves

Any ticket that moves a store or introduces a new storage call must run through this before merge:

1. Confirm the source or destination module does **not** invent a new object path. If a new path is needed, add a row to the "Object-path contracts" table above, update the relevant migration helper, and land both in the same PR.
2. Confirm the route that serves the object still runs the project guard before issuing a signed URL or reading bytes.
3. If the move touches `storage_service.py`, rerun the cross-user access smoke checklist for the affected bucket.
4. If the move adds a new bucket, it must land the bucket in a new migration + update this file + update the owning data-bearing `CHARTER.md`.

## Files referenced

- `backend/supabase/migrations/00002_storage_buckets.sql`
- `backend/supabase/migrations/00007_brand_assets.sql`
- `backend/supabase/migrations/00010_brand_to_user_level.sql`
- `backend/supabase/init.sql` (self-hosted bootstrap)
- `backend/app/providers/supabase/storage.py`
- `backend/app/api/sources/routes.py` (`download_source`, `upload_source`)
- `backend/app/api/brand/routes.py`
- `backend/app/api/studio/` (category routes)
- `backend/app/__init__.py` (`enforce_auth` before-request hook)
- `backend/app/projects/store.py` (`has_project_access`)
