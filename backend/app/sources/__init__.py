"""
Sources domain root.

Charter (NBB-104): Source ingestion, extraction, indexing, search, citations,
and analysis slices (CSV, database, Freshdesk, deep research). Owns the source
pipeline and the file-format ownership map.

Allowed imports:
- `api/` route modules, `chat/` (for search/citation surfaces), and `studio/`
  (for content generation consumption) import this package's public surface.
- This package may depend on `providers/` (storage, vector DB, external
  transcription/web fetch clients), `connectors/` for configured integrations,
  `auth/`, `projects/`, and `background/`.
- This package must not reach into another domain's internals.

Migration source: legacy source processing and source AI modules are being
drained from `backend/app/services/` by `NBB-401` through `NBB-808`.
"""
