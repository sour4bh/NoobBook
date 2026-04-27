# `brand/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which storage buckets, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, bucket, or JSONB field below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` and `backend/supabase/STORAGE_CONTRACTS.md` to spot-check.

**Migration source (NBB-209D):** brand stores formerly lived under `backend/app/services/data_services/`; `NBB-209D` moved them here and `NBB-802` removed the dead residue.

## Tables owned by `brand/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `brand_config` | `backend/supabase/migrations/00007_brand_assets.sql`, re-scoped to user in `00010_brand_to_user_level.sql`, then to workspace in `00024_workspace_brand_settings.sql` | Hosted: RLS `user_has_workspace_access(workspace_id, auth.uid())` for reads; `user_can_manage_workspace(...)` for writes. Self-hosted: backend workspace guard. | One row per workspace (`UNIQUE (workspace_id)`). |
| `brand_assets` | `00007_brand_assets.sql`, re-scoped to user in `00010_brand_to_user_level.sql`, then to workspace in `00024_workspace_brand_settings.sql` | Hosted: same workspace membership/manager RLS as `brand_config`. Self-hosted: backend workspace guard. | Asset types: logo/icon/font/image (CHECK constraint). |

## Storage buckets owned by `brand/`

| Bucket | Object path (runtime) | Serving route | Notes |
|---|---|---|---|
| `brand-assets` | `{workspace_id}/brand/{asset_id}/{filename}` for new uploads | `GET /api/v1/brand/...` routes in `backend/app/api/brand/routes.py` stream bytes through `storage_service.download_brand_asset_by_path` | Runtime path and migration helper (`generate_brand_asset_path` in 00024) agree with workspace-membership storage policies. Existing rows keep their stored `file_path` so already-uploaded objects remain readable. |

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

- Entry guard: brand routes are workspace-scoped. They resolve the selected workspace with `resolve_workspace_context(...)`; read routes require workspace membership and write routes require workspace owner/admin.
- RLS of record (hosted): `brand_assets` and `brand_config` policies in `00024_workspace_brand_settings.sql` use workspace membership for reads and workspace manager role for writes.
- Self-hosted mode still enforces the same rule in backend route code. Brand bucket storage policy expects the first object segment to be the workspace id for new objects.

## Data-move pre-flight (NBB-209D)

1. Preserve the `UNIQUE (workspace_id)` invariant on `brand_config`.
2. New object paths must use `{workspace_id}/brand/{asset_id}/{filename}`. Existing rows should be read through their stored `file_path`.
3. `delete_workspace_brand_assets` in `storage_service.py` iteratively scans folders; preserve the folder-scan semantics so partial deletions don't leak assets.
4. Brand is workspace-level. Do not reintroduce user- or project-scoped brand state without a ticket that amends the product decision from NBB-010.

## Cross-reference

- Import/dependency charter: `backend/app/brand/__init__.py`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage bucket and object-path contracts: `backend/supabase/STORAGE_CONTRACTS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
