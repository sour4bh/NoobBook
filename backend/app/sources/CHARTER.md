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

---

# Pipeline skeleton and file-format ownership (NBB-401)

**Owner:** NBB-401 overlays the source pipeline skeleton and file-format ownership map on top of the NBB-204 data-bearing charter above and the package-level import/dependency charter in `backend/app/sources/__init__.py` (authored by NBB-104). Read the `__init__.py` charter first, then the NBB-204 sections above; this section finalizes the pipeline-shaped destinations that downstream source tickets (`NBB-402`, `NBB-403`, `NBB-702`) move code into.

**Scope:** the `sources/` domain expresses a pipeline — upload, ingestion, extraction, chunking, indexing, citations, and analysis — and owns the file-format operations that express source behavior (PDF, PPTX, DOCX, image, link, YouTube, audio, and analysis slices). Low-level external API clients stay under `providers/`. Configured external capabilities (for example Google Drive ingestion hand-off, Notion import) stay under `connectors/`. The pipeline stage narrative lives in `backend/app/sources/README.md`; the ownership map is locked here.

## Rejected default homes

`platform/files/` and `providers/files/` are explicitly rejected as default homes for any file-format helper on this map. There is no generic file-adapter root; source format operations live under `sources/<format>/` and follow this decision map, provider-neutral IO primitives stay under `providers/` near the protocol they speak, and configured product capabilities stay under `connectors/<name>/`. Any newly discovered source file-format helper must be added to this map before it moves.

## Decision map

Copied verbatim from `docs/tickets/epics/NBB-004.md#nbb-401`. Downstream tickets execute these moves; this section locks the destinations.

| Current code/concept | Target owner under `backend/app/` | Locked decision |
|---|---|---|
| `utils/file_utils.py` | `sources/file_contract.py` | Owns allowed extension, source category, MIME, and upload size contract. Frontend mirrors this through `NBB-205`. Locked target: not `backend/app/api/`, not `platform/files/`, not `providers/files/`. |
| `utils/citation_utils.py` | `sources/citations.py` | Source chunk/citation lookup. Preserve `[[cite:chunk_id]]`; not chat-owned. Verified importer is `backend/app/api/sources/content.py`; docstring-only mentions in text utilities do not change ownership. |
| `utils/source_content_utils.py` | `sources/content.py` | Source-content read helper used by studio/agent code. |
| `utils/pdf_utils.py` | `sources/pdf/ops.py` | PDF page count and page-byte operations for source extraction. |
| `utils/pptx_utils.py` | `sources/pptx/ops.py` | PPTX conversion operations for source extraction. |
| `utils/docx_utils.py` | `sources/docx/ops.py` | DOCX text extraction for source ingestion. |
| `ai_services/pdf_service.py` | `sources/pdf/extract.py` | PDF extraction behavior. |
| `ai_services/pptx_service.py` | `sources/pptx/extract.py` | PPTX extraction behavior. |
| `ai_services/image_service.py` | `sources/image/extract.py` | Source image extraction behavior; model/client calls stay behind providers/connectors. |
| Link/URL source orchestration | `sources/link/` | URL ingestion and extraction behavior. Vendor search/fetch clients stay outside sources. |
| YouTube source orchestration | `sources/youtube/` | Source-side transcript orchestration. Vendor/library client code stays under provider ownership. |
| Audio source orchestration | `sources/audio/` | Source-side transcription flow. ElevenLabs client code stays under provider ownership. |
| Deep research source processing | `sources/analysis/research/` | Source analysis slice; implementation move happens in `NBB-403`. |
| `presentation_export_utils.py` | Not `NBB-401`; `NBB-502`/`NBB-705D` | Studio export ownership. |
| `screenshot_utils.py` | Not `NBB-401`; `NBB-502`/`NBB-705D` | Studio screenshot/export ownership. |
| `path_utils.py` | Not `NBB-401`; approved exception unless `NBB-705E` rehomes it | Cross-cutting filesystem path helper. |
| `logger.py`, `utils/text/` | Not `NBB-401`; approved exceptions unless `NBB-705E` rehomes them | Bootstrap logging and cohesive text package. |

- `platform/files/` and `providers/files/` are not targets for any row in this map.
- Any newly discovered source file-format helper must be added to this map before it moves.

## Pipeline destinations at a glance

Downstream tickets (`NBB-402`, `NBB-403`) land code at these locked paths. Full pipeline-stage narrative is in `backend/app/sources/README.md`.

| Stage | Destination module or directory | Locked by |
|---|---|---|
| Upload contract | `sources/file_contract.py` | NBB-401 map (above) |
| Upload handling | `sources/upload/file.py` | `NBB-402` target map |
| Ingestion / pipeline orchestration | `sources/pipeline.py` | `NBB-402` target map |
| Extraction (per format) | `sources/pdf/extract.py`, `sources/pptx/extract.py`, `sources/image/extract.py`, `sources/docx/ops.py` (text), `sources/link/`, `sources/youtube/`, `sources/audio/` | NBB-401 map (above) |
| Format low-level ops | `sources/pdf/ops.py`, `sources/pptx/ops.py`, `sources/docx/ops.py` | NBB-401 map (above) |
| Catalog / source metadata surface | `sources/catalog.py` | `NBB-402` target map |
| Indexing | `sources/index.py` | `NBB-402` target map |
| Citations | `sources/citations.py` | NBB-401 map (above) |
| Source-content reads | `sources/content.py` | NBB-401 map (above) |
| Analysis slices | `sources/analysis/csv/`, `sources/analysis/database/`, `sources/analysis/freshdesk/`, `sources/analysis/research/` | `NBB-403` target map |

Forbidden filename tokens in the migrated source tree (per `NBB-402`): `service.py`, `manager.py`, `processor.py`, `handler.py`, `helper.py`, `util.py`. Forbidden vague verb fragments: `handle`, `process`, `manage`, `execute`, `perform`, `do`. The destination names above are locked; do not rename them in passing.

## Boundaries with `providers/` and `connectors/`

- File-format parsing and extraction are domain behavior under `sources/` — `providers/CHARTER.md` already pins this boundary; do not re-open it.
- Raw external clients (Anthropic vision, OpenAI embeddings, Pinecone, ElevenLabs, Tavily, YouTube transcript fetch, Supabase storage) remain under `providers/`. `sources/` imports these as provider-neutral runtime primitives.
- Configured product ingestion hand-offs (Google Drive download, connector attachment fetch) live under `connectors/<name>/` and pass bytes into `sources/` ingestion public surface. Connectors must not parse file formats.
- The Supabase storage path builder stays a domain-reviewed provider seam for the `raw-files`, `processed-files`, and `chunks` buckets — see NBB-204 section above and `providers/CHARTER.md`.

## Skeleton markers

Empty `__init__.py` files with a one-line docstring naming the downstream owner ticket mark the planned subtrees (no implementation modules yet). Present markers:

- `sources/upload/__init__.py` — owner `NBB-402`.
- `sources/pdf/__init__.py` — owner `NBB-402`.
- `sources/pptx/__init__.py` — owner `NBB-402`.
- `sources/docx/__init__.py` — owner `NBB-402`.
- `sources/image/__init__.py` — owner `NBB-402`.
- `sources/link/__init__.py` — owner `NBB-402`.
- `sources/youtube/__init__.py` — owner `NBB-402`.
- `sources/audio/__init__.py` — owner `NBB-402`.
- `sources/analysis/__init__.py` — owner `NBB-403`.
- `sources/analysis/research/__init__.py` — owner `NBB-403`.

`NBB-402` and `NBB-403` add the module files listed in the decision map above. No `.py` implementation modules land in this ticket.

## Cross-reference

- Ticket body: `docs/tickets/epics/NBB-004.md#nbb-401`.
- Downstream moves: `docs/tickets/epics/NBB-004.md#nbb-402` (ingestion, catalog, index, citations, content, file contract), `docs/tickets/epics/NBB-004.md#nbb-403` (CSV/database/Freshdesk/research analysis slices), `docs/tickets/epics/NBB-007.md#nbb-702` (source/citation verification).
- Providers/connectors boundary: `backend/app/providers/CHARTER.md`, `backend/app/connectors/CHARTER.md`.
- Structure rules: `STRUCTURE.md` Canonical Backend Roots + Placement Checklist + Frozen Destinations.
- Pipeline narrative and subtree responsibilities: `backend/app/sources/README.md`.
