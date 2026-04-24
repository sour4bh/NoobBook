# `sources/` pipeline skeleton (NBB-401)

This file narrates the source pipeline stages and the subtree that owns each stage. The ownership map and locked destinations live in `backend/app/sources/CHARTER.md` under the `NBB-401` section. The package-level import rules live in `backend/app/sources/__init__.py` (NBB-104). The data-bearing overlay (tables, RLS, buckets, JSONB contracts) lives in the NBB-204 section at the top of `CHARTER.md`.

Read order: `__init__.py` charter → `CHARTER.md` (NBB-204 + NBB-401 sections) → this file.

## What `sources/` owns

The `sources/` domain owns the full lifecycle of a user-provided source from upload through analysis:

1. **Upload** — accept file, URL, pasted text, or connector-delivered bytes; enforce the upload contract (extension, MIME, size, source category).
2. **Ingestion** — run the source through the appropriate extractor, persist metadata, and route to background workers when needed.
3. **Extraction** — turn raw bytes into text-plus-page-markers per format (PDF, PPTX, DOCX, image, link, YouTube, audio, pasted text).
4. **Chunking** — split extracted text into ~200-token chunks for embeddings (uses `utils/text/chunking.py` today; `utils/text/` is an approved exception under `NBB-705E` review).
5. **Indexing** — embed chunks, upsert to the vector store, and record per-source embedding metadata.
6. **Citations** — resolve `[[cite:chunk_id]]` markers back to source chunk content for the frontend tooltip; preserve the chunk-ID format `{source_id}_page_{page}_chunk_{n}`.
7. **Analysis** — source-scoped analysis slices (CSV, database, Freshdesk, deep research) that operate on source content after ingestion.

## Pipeline stage → subtree

Destinations are locked by `NBB-401` (file-format ownership map, in `CHARTER.md`) and `NBB-402` / `NBB-403` (target maps in `docs/tickets/epics/NBB-004.md`). `NBB-401` only adds the skeleton markers; the implementation modules land under their owning ticket.

| Stage | Subtree | Locked destinations |
|---|---|---|
| Upload contract | `sources/` | `sources/file_contract.py` |
| Upload handling | `sources/upload/` | `sources/upload/file.py` |
| Ingestion orchestration | `sources/` | `sources/pipeline.py` |
| Catalog / source surface | `sources/` | `sources/catalog.py` |
| Indexing | `sources/` | `sources/index.py` |
| Citations | `sources/` | `sources/citations.py` |
| Source-content reads | `sources/` | `sources/content.py` |
| PDF format | `sources/pdf/` | `sources/pdf/ops.py`, `sources/pdf/extract.py` |
| PPTX format | `sources/pptx/` | `sources/pptx/ops.py`, `sources/pptx/extract.py` |
| DOCX format | `sources/docx/` | `sources/docx/ops.py` |
| Image format | `sources/image/` | `sources/image/extract.py` |
| Link / URL format | `sources/link/` | orchestration module(s) owned by `NBB-402` |
| YouTube format | `sources/youtube/` | orchestration module(s) owned by `NBB-402` |
| Audio format | `sources/audio/` | orchestration module(s) owned by `NBB-402` |
| Analysis slices | `sources/analysis/<feature>/` | `sources/analysis/csv/`, `sources/analysis/database/`, `sources/analysis/freshdesk/`, `sources/analysis/research/` (per `NBB-403`) |

Skeleton markers present today: `sources/upload/__init__.py`, `sources/pdf/__init__.py`, `sources/pptx/__init__.py`, `sources/docx/__init__.py`, `sources/image/__init__.py`, `sources/link/__init__.py`, `sources/youtube/__init__.py`, `sources/audio/__init__.py`, `sources/analysis/__init__.py`, `sources/analysis/research/__init__.py`. Each is an empty module with a one-line docstring naming the downstream owner ticket.

## What does not live under `sources/`

- **Low-level external API clients** (Anthropic vision, OpenAI embeddings, Pinecone, ElevenLabs, Tavily, YouTube transcript fetch, Supabase storage). These stay under `providers/` per `NBB-206`. `sources/` imports them as provider-neutral runtime primitives.
- **Configured product ingestion hand-offs** (Google Drive download, connector attachment fetch, Notion/Jira/Freshdesk product orchestration). These stay under `connectors/<name>/` per `NBB-206`. A connector may fetch bytes and hand them to `sources/`; it must not parse file formats.
- **Studio export and screenshot helpers** (`presentation_export_utils.py`, `screenshot_utils.py`). These are studio-owned under `NBB-502` / `NBB-705D`.
- **Cross-cutting helpers** (`path_utils.py`, `logger.py`, `utils/text/`). These are approved exceptions unless `NBB-705E` rehomes them.

`platform/files/` and `providers/files/` are explicitly rejected as default homes for any file-format helper. There is no generic file-adapter root; source format operations live under `sources/<format>/` per the decision map in `CHARTER.md`.

## Boundaries and dependency direction

- `api/` route modules, `chat/`, `studio/`, and `connectors/<name>/` call the `sources/` public surface for catalog, ingestion hand-off, citation lookup, content reads, and analysis invocation.
- `sources/` may depend on `providers/`, `connectors/`, `auth/`, `projects/`, and `background/`. It must not reach into another domain's internals.
- Rich import-direction enforcement lands in `NBB-704A` and `NBB-704B`.

## Out of scope for NBB-401

- Moving implementations. `NBB-402` and `NBB-403` own mechanical moves via refactory; this ticket only creates skeleton markers and documents destinations.
- Changing extraction behavior.
- Prompt and tool JSON ownership. Those follow `NBB-207B` (prompts) and `NBB-207C` (tools).
- Store moves. Chat/message/project/brand/connector stores follow `NBB-209A`–`NBB-209E`; source-adjacent store movement (if discovered) is coordinated through `NBB-402` and the NBB-204 data-bearing charter above.

## Cross-reference

- Full ticket body: `docs/tickets/epics/NBB-004.md#nbb-401`.
- Downstream tickets: `docs/tickets/epics/NBB-004.md#nbb-402`, `#nbb-403`; verification in `docs/tickets/epics/NBB-007.md#nbb-702`.
- Providers/connectors boundary: `backend/app/providers/CHARTER.md`, `backend/app/connectors/CHARTER.md`.
- Structure rules: `STRUCTURE.md` Canonical Backend Roots, Placement Checklist, Frozen Destinations.
- Data-bearing overlay: the `NBB-204` section at the top of `backend/app/sources/CHARTER.md`.
