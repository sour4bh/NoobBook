"""
Source Services - legacy migration source.

Submodules `source_upload/` and `source_processing/` still live in this
package and remain in active use; they are explicitly out of scope for
NBB-706. The lazy `__getattr__` re-export shim that exposed `source_service`,
`SourceService`, and `source_index_service` was removed in NBB-706 — those
names now import from their domain homes:

- `source_service`     -> `app.sources.catalog.source_service`
- `SourceService`      -> `app.sources.catalog.SourceCatalog`
- `source_index_service` -> `app.sources.index`

Future ownership work can collapse this package into the source domain
once `source_upload/` and `source_processing/` are migrated.
"""
