# `sources/` data-bearing charter (NBB-204)

**Owner:** NBB-204 owns the data-bearing overlay for this root: which tables, which RLS/guard invariants, which storage buckets, which JSONB contracts belong here. The package-level import/dependency charter in `__init__.py` (authored by NBB-104) still applies; read it first.

**Validation approach:** every table, bucket, or JSONB field below must point at a migration file. Every access-guard claim must point at a route or service file. Reviewer uses `backend/supabase/migrations/OWNERS.md` and `backend/supabase/STORAGE_CONTRACTS.md` to spot-check.

**Migration source:** source metadata currently lives under `backend/app/services/data_services/` and `backend/app/services/source_services/`; `NBB-402` moves stores and `NBB-403` consolidates analysis slices.

## Tables owned by `sources/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `sources` | `backend/supabase/migrations/00001_initial_schema.sql`, RLS in `00003_rls_policies.sql` | Hosted: RLS via `sources.project_id -> projects.user_id` subquery. Self-hosted: backend guard on project route entry. | Type enum: PDF/DOCX/PPTX/IMAGE/AUDIO/LINK/YOUTUBE/TEXT/RESEARCH. Status enum: uploaded/processing/embedding/ready/error/cancelled. |
| `chunks` | `00001_initial_schema.sql`, RLS in `00003_rls_policies.sql` | Hosted: RLS via `chunks.source_id -> sources.project_id -> projects.user_id`. Self-hosted: backend guard. | Chunk id format `{source_id}_page_{page}_chunk_{n}` is the citation contract consumed by chat; shape owner: NBB-205. |
| `freshdesk_tickets` | `00016_freshdesk_tickets.sql`, flattened to global in `00017_freshdesk_global_tickets.sql` | **No RLS.** Intentionally global per deployment. Access is guarded by the project-scoped route that invokes the Freshdesk analysis tool; the caller has already passed `has_project_access`. | NBB-403 owns the analysis slice; NBB-204 records the decision to keep this store global. |

## Storage buckets owned by `sources/`

| Bucket | Object path (runtime) | Serving route | Notes |
|---|---|---|---|
| `raw-files` | `{project_id}/{source_id}/{filename}` | `GET /api/v1/projects/{project_id}/sources/{source_id}/download` -> redirect to signed URL | See "Known inconsistency" in `backend/supabase/STORAGE_CONTRACTS.md`. |
| `processed-files` | `{project_id}/{source_id}/{source_id}.txt` | Internal reads during ingestion/search | Same inconsistency. |
| `chunks` | `{project_id}/{source_id}/{chunk_id}.txt` | `GET /api/v1/projects/{project_id}/citations/{chunk_id}` returns chunk content for citation tooltips | Same inconsistency. |

Path builder module: `backend/app/services/integrations/supabase/storage_service.py` (`_build_path`). Do not introduce new path builders for these buckets in sibling modules.

## JSONB contracts owned here (shape lives in NBB-205)

| Column | Table | Defined in | Purpose |
|---|---|---|---|
| `sources.embedding_info` | `sources` | 00001 | Pinecone vector IDs + counts. |
| `sources.summary_info` | `sources` | 00001 | AI-generated summary metadata loaded by `context_loader.py`. |
| `freshdesk_tickets.custom_fields` | `freshdesk_tickets` | 00016, 00017 | Flexible Freshdesk custom field passthrough. |

## Access guard of record

- Entry guard: `@before_request` enforcement in `backend/app/__init__.py` calls `project_service.has_project_access(project_id, user_id)` for every `/api/v1/projects/{id}/sources/...` and `/api/v1/projects/{id}/citations/{chunk_id}` route.
- RLS defence-in-depth (hosted): `00003_rls_policies.sql` gates `sources` and `chunks` via project-ownership subqueries. A missed guard in a new route is still blocked by RLS in hosted deployments.
- Self-hosted mode has no RLS on `sources`/`chunks`; the project guard is the only barrier.
- Raw file download cross-user protection: the `GET .../download` route looks up the source metadata first (which is RLS-gated in hosted mode) before requesting a signed URL. In self-hosted mode the project guard blocks cross-user access before the metadata lookup runs. The storage-layer RLS on `raw-files` is **advisory** for this bucket because runtime paths do not include `{user_id}/` and service-role writes bypass RLS — see "Known inconsistency" in `STORAGE_CONTRACTS.md`.

## Data-move pre-flight (NBB-402, NBB-403, NBB-702)

1. Do not change the chunk ID format (`{source_id}_page_{page}_chunk_{n}`). Chat citations depend on it.
2. Preserve status enum values; any new state must be added in a migration with a CHECK constraint update.
3. When NBB-403 consolidates analysis slices (`csv/`, `database/`, `freshdesk/`, `deep_research/`), respect the global store decision for `freshdesk_tickets`. Do not introduce per-user scoping without a ticket that amends the product decision.
4. File-format specific storage (new buckets) requires a new migration + a STORAGE_CONTRACTS.md update + a new row in this table.

## Cross-reference

- Import/dependency charter: `backend/app/sources/__init__.py`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage bucket and object-path contracts: `backend/supabase/STORAGE_CONTRACTS.md`.
- Access smoke checklist: `docs/tickets/checklists/data_access_smoke.md`.
