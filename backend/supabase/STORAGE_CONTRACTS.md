# Supabase storage buckets and object-path contracts

**Owner (NBB-204):** Backend data-contracts lane. Owns the bucket inventory, object-path conventions, the serving-route map, and the guard-of-record for each bucket. Domain-owned storage clients (`sources/`, `studio/`, `brand/`) must consult this file before renaming an object path or adding a new bucket.

**Validation approach:** every entry below must point at (a) the defining migration, (b) the path builder in runtime code, and (c) the route that serves the object or redirects to a signed URL. Pull requests that touch any of those three must cite this file in the review description.

**Cross-reference:** table contracts and RLS status live in `migrations/OWNERS.md`. Cross-user smoke checklist lives in `../../docs/tickets/checklists/data_access_smoke.md`.

## Bucket inventory

| Bucket | Public? | Size limit | Defined in | Storage policy (hosted) | Storage policy (self-hosted) | Path builder | Owning domain |
|---|---|---|---|---|---|---|---|
| `raw-files` | false | 100 MB | `migrations/00002_storage_buckets.sql`; owner-prefix reconciliation in `00021_storage_owner_paths.sql`; workspace-prefix reconciliation in `00023_workspace_membership.sql` | `user_can_edit_project((storage.foldername(name))[2]::uuid, auth.uid())` for writes; `user_has_project_access(...)` for reads | Same workspace/project policy in `init.sql` | `_build_source_path(project_id, source_id, filename)` in `backend/app/providers/supabase/storage.py` (runtime workspace prefix lands in NBB-1004) | `sources/` |
| `processed-files` | false | 100 MB | `migrations/00002_storage_buckets.sql`; `00021_storage_owner_paths.sql`; `00023_workspace_membership.sql` | Same workspace/project shape as `raw-files` | Same workspace/project policy | `_build_source_path(project_id, source_id, filename)` | `sources/` |
| `chunks` | false | 10 MB | `migrations/00002_storage_buckets.sql`; `00021_storage_owner_paths.sql`; `00023_workspace_membership.sql` | Same workspace/project shape | Same workspace/project policy | `_build_source_path(project_id, source_id, chunk_id)` (same helper, called with chunk filenames) | `sources/` (indexing slice) |
| `studio-outputs` | false | 500 MB | `migrations/00002_storage_buckets.sql`; `00021_storage_owner_paths.sql`; `00023_workspace_membership.sql` | Same workspace/project shape | Same workspace/project policy | `_build_studio_path(project_id, job_type, job_id, filename)` and `_build_ai_image_path(project_id, filename)` | `studio/` |
| `brand-assets` | false | n/a (no limit declared in migration; 00007 + 00010 own the table-side path) | `migrations/00007_brand_assets.sql` + path update in `00010_brand_to_user_level.sql`; permissive-policy removal in `00021_storage_owner_paths.sql` | Same `auth.uid()` first-folder rule | Same owner-prefix policy | `_build_brand_path(user_id, asset_id, filename)` | `brand/` |

## Object-path contracts

| Bucket | Object path (today) | Migration generator | Runtime builder | Notes |
|---|---|---|---|---|
| `raw-files` | `{workspace_id}/{project_id}/{source_id}/{filename}` | `generate_raw_file_path(workspace_id, project_id, source_id, filename)` in 00023 | `_build_source_path(project_id, source_id, filename)` | Existing user-prefixed objects are backfilled by `00023_workspace_membership.sql`. Runtime builder update lands with project guard work in NBB-1004. |
| `processed-files` | `{workspace_id}/{project_id}/{source_id}/{source_id}.txt` | `generate_processed_file_path` in 00023 defines this shape | `_build_source_path(project_id, source_id, filename)` | Existing user-prefixed source metadata paths are backfilled by `00023_workspace_membership.sql`. |
| `chunks` | `{workspace_id}/{project_id}/{source_id}/{chunk_id}.txt` | `generate_chunk_file_path` in 00023 defines this shape | `_build_source_path(project_id, source_id, chunk_id)` | Chunk id format itself remains unchanged. |
| `studio-outputs` | `{workspace_id}/{project_id}/studio/{job_type}/{job_id}/{filename}` and `{workspace_id}/{project_id}/ai-images/{filename}` | `generate_studio_output_path` and `generate_ai_image_path` in 00023 define these shapes | `_build_studio_path(project_id, job_type, job_id, filename)` and `_build_ai_image_path(project_id, filename)` | Existing user-prefixed objects are backfilled by `00023_workspace_membership.sql`. |
| `brand-assets` | `{user_id}/brand/{asset_id}/{filename}` | `generate_brand_asset_path(user_id, asset_id, filename)` in 00010 matches | `_build_brand_path(user_id, asset_id, filename)` | Consistent. |

## Serving-route and guard map

| Bucket | Read surface | Write surface | Guard of record |
|---|---|---|---|
| `raw-files` | `GET /api/v1/projects/{project_id}/sources/{source_id}/download` (`backend/app/api/sources/routes.py` `download_source`) redirects to signed URL from `storage_service.get_raw_file_url` | `POST /api/v1/projects/{project_id}/sources` (`upload_source` in `backend/app/api/sources/routes.py`) | `@before_request` enforce in `backend/app/__init__.py` -> `project_service.has_project_access(project_id, user_id)`. Storage RLS also requires explicit `project_members` access to the second object segment (`project_id`). |
| `processed-files` | Internal only (read during ingestion/search in `backend/app/sources/` and chat context loaders) | Ingestion pipeline writes via `storage_service.upload_processed_file` | Project guard + RLS on the `sources` row the path is derived from. |
| `chunks` | Internal only (read by `source_search_executor` and the chunk citation route below) | Ingestion pipeline writes via `storage_service.upload_chunk` | Project guard + RLS on `chunks`. Citation lookup path: `GET /api/v1/projects/{project_id}/citations/{chunk_id}` (see `backend/app/api/sources/`). |
| `studio-outputs` | `GET /api/v1/projects/{project_id}/studio/{category}/...` category routes in `backend/app/api/studio/` generate signed URLs via `storage_service.get_studio_signed_url`/`get_studio_public_url`, or stream bytes through backend routes | Studio generators write via `storage_service.upload_studio_file` / `upload_studio_binary`; CSV analysis writes generated images through `upload_ai_image` | Project guard plus workspace/project-prefixed storage keys. `studio_jobs` has no table RLS (see `migrations/OWNERS.md`), so route-level project guard remains required before signed URL issuance or byte streaming. |
| `brand-assets` | `GET /api/v1/brand/...` routes in `backend/app/api/brand/routes.py` stream bytes through `storage_service.download_brand_asset` | `POST /api/v1/brand/...` upload surfaces | Brand routes are user-scoped through authenticated identity; storage RLS also requires first segment `user_id`. |

## Owner-prefix reconciliation

`NBB-914` resolved the prior mismatch between runtime object keys and storage
RLS policy shape. Runtime storage builders now put `user_id` in the first
object-key segment for source files, chunk files, studio outputs, generated
analysis images, and brand assets. Migration `00021_storage_owner_paths.sql`
backfills existing unprefixed `storage.objects.name` values and source metadata
paths where the first segment was a project id.

`NBB-1002` supersedes that shape for project-owned buckets only. Source, chunk,
studio, and generated analysis object keys become
`{workspace_id}/{project_id}/...`, and storage RLS checks explicit project
membership against the second segment. Brand assets remain user-prefixed until
the workspace settings/brand migration in `NBB-1006`.

The backend still uses a service-role Supabase client when configured, so
storage RLS is defence-in-depth rather than the only barrier. The guard of
record for project-owned buckets remains `project_service.has_project_access`
on `/api/v1/projects/{project_id}/...` routes. Brand routes are user-scoped and
look up assets by authenticated `user_id`.

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
