# `brand/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which storage buckets, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, bucket, or JSONB field below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` and `backend/supabase/STORAGE_CONTRACTS.md` to spot-check.

**Migration source (NBB-209D):** brand stores formerly lived under `backend/app/services/data_services/`; `NBB-209D` moved them here and `NBB-802` removed the dead residue.

## Tables owned by `brand/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `brand_config` | `backend/supabase/migrations/00007_brand_assets.sql`, re-scoped to user in `00010_brand_to_user_level.sql` | Hosted: RLS `user_id = auth.uid()` (direct match since 00010). Self-hosted: backend auth identity. | One row per user (`UNIQUE (user_id)`). Workspace-level brand settings shared across all projects of that user. |
| `brand_assets` | `00007_brand_assets.sql`, re-scoped to user in `00010_brand_to_user_level.sql` | Hosted: RLS `user_id = auth.uid()`. Self-hosted: backend auth identity. | Asset types: logo/icon/font/image (CHECK constraint). |

## Storage buckets owned by `brand/`

| Bucket | Object path (runtime) | Serving route | Notes |
|---|---|---|---|
| `brand-assets` | `{user_id}/brand/{asset_id}/{filename}` | `GET /api/v1/brand/...` routes in `backend/app/api/brand/routes.py` stream bytes through `storage_service.download_brand_asset` | Runtime path and migration helper (`generate_brand_asset_path` in 00010) agree with the `auth.uid()::text == folder[1]` storage policy; `00021_storage_owner_paths.sql` removes the permissive self-hosted policy. |

Path builder: `backend/app/providers/supabase/storage.py::_build_brand_path`. Do not introduce new path builders for this bucket elsewhere.

## JSONB contracts owned here (shape lives in NBB-205)

| Column | Table | Defined in | Purpose |
|---|---|---|---|
| `brand_config.colors` | `brand_config` | 00007 | Palette with primary/secondary/accent/background/text/custom. |
| `brand_config.typography` | `brand_config` | 00007 | Fonts, sizes, line heights. |
| `brand_config.spacing` | `brand_config` | 00007 | Base / small / large / section. |
| `brand_config.guidelines` | `brand_config` | 00007 | Markdown brand guidelines. |
| `brand_config.best_practices` | `brand_config` | 00007 | Brand dos / donts arrays. |
| `brand_config.voice` | `brand_config` | 00007 | Tone, personality, keywords. |
| `brand_config.feature_settings` | `brand_config` | 00007 | Per-feature brand-application toggles. |
| `brand_assets.metadata` | `brand_assets` | 00007 | Dimensions / font metadata / other per-asset fields. |

## Access guard of record

- Entry guard: brand routes are user-scoped (not project-scoped). They rely on the authenticated identity set by the auth stack (`get_request_identity` in `backend/app/auth/identity.py`); the `@before_request` project-access guard does not apply because the URL prefix is `/api/v1/brand/...`, not `/api/v1/projects/{id}/...`. Any new brand route that takes a `{project_id}` must add the project guard.
- RLS of record (hosted): `brand_assets` and `brand_config` policies in `00010_brand_to_user_level.sql` use `user_id = auth.uid()`.
- Self-hosted mode has no RLS on these tables; the backend-authenticated user id is the only table barrier. Brand bucket storage policy still requires the first object segment to equal `auth.uid()` when clients access storage directly.

## Data-move pre-flight (NBB-209D)

1. Preserve the `UNIQUE (user_id)` invariant on `brand_config` when moving the store.
2. Preserve the object-path contract `{user_id}/brand/{asset_id}/{filename}` — it is the only one consistent across migrations, runtime, and storage policy.
3. `delete_user_brand_assets` in `storage_service.py` iteratively scans folders; if the move replaces it, preserve the folder-scan semantics so partial deletions don't leak assets.
4. Brand is workspace-level (per user). Do not reintroduce project-scoped paths without a ticket that amends the product decision from 00010.

## Cross-reference

- Import/dependency charter: `backend/app/brand/__init__.py`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage bucket and object-path contracts: `backend/supabase/STORAGE_CONTRACTS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
