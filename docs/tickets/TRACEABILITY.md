# Ticket Traceability

This file preserves the review trail after the flat `NBB-001` through `NBB-018` tickets were archived under `docs/tickets/archive/legacy-flat/`.

Note: the legacy flat tickets were archived before the new epic IDs were introduced. If the archive was created before these files were tracked on a branch, there may be no prior committed file history for `git log --follow` to preserve.

## Decision Maps

These maps are indexed here for review, but the owning ticket body is the implementation source of truth.

| Decision map | Source of truth |
|---|---|
| `base/` and `shared/` charters | `NBB-104` |
| Approved backend roots and legacy-root exceptions | `NBB-104`, `NBB-705E` |
| Auth identity, middleware, query-token policy | `NBB-201` |
| Permission fail-closed behavior | `NBB-202A` |
| Tool capability policy | `NBB-202B`, `NBB-303` |
| Prompt JSON ownership | `NBB-207B` |
| Tool JSON ownership, including all current tool families | `NBB-207C` |
| Prompt/tool loader registry and shims | `NBB-207A` |
| Domain store ownership for former `data_services/` | `NBB-209A` through `NBB-209E` |
| Chat public surface and split layout | `NBB-301`, `NBB-302`, `NBB-304` |
| Source/file-format ownership | `NBB-401` |
| Studio taxonomy | `NBB-501A` |
| Studio item registry | `NBB-501B` |
| Studio item layer pattern | `NBB-502` |
| Utility drain map and approved exceptions | `NBB-705A` through `NBB-705E` |

## Legacy Flat Ticket Mapping

| Legacy ID | Legacy title | New owner |
|---|---|---|
| `NBB-001` | Freeze legacy buckets | `NBB-101`, `NBB-102`, `NBB-103`, `NBB-104`, `NBB-105`, `NBB-109` |
| `NBB-002` | Create backend target packages | `NBB-104`, `NBB-206` |
| `NBB-003` | Auth consolidation | `NBB-201`, `NBB-202A`, `NBB-202B` |
| `NBB-004` | Platform extraction | `NBB-206`, `NBB-208A`, `NBB-208B`, `NBB-401`, `NBB-705C` |
| `NBB-005` | Chat migration | `NBB-301`, `NBB-302`, `NBB-303`, `NBB-304` |
| `NBB-006` | Sources migration | `NBB-401`, `NBB-402`, `NBB-702` |
| `NBB-007` | Structured analysis | `NBB-203`, `NBB-403`, `DEFERRED.md` `D-002` |
| `NBB-008` | Studio skeleton | `NBB-501A`, `NBB-501B`, `NBB-502` |
| `NBB-009` | Studio blog pilot | `NBB-503` |
| `NBB-010` | Studio documents | `NBB-504` |
| `NBB-011` | Studio marketing | `NBB-505` |
| `NBB-012` | Studio design/logo | `NBB-506` |
| `NBB-013` | Studio learning/media | `NBB-507` |
| `NBB-014` | Smaller domains | `NBB-209A` through `NBB-209E`, `NBB-601`, `NBB-603` |
| `NBB-015` | Utils cleanup | `NBB-705A` through `NBB-705E` |
| `NBB-016` | Frontend shells | `NBB-105`, `NBB-601`, `NBB-602` |
| `NBB-017` | Frontend lib/contexts | `NBB-603`, `NBB-604` |
| `NBB-018` | Tests/shims/delete legacy | `NBB-103`, `NBB-701`, `NBB-702`, `NBB-703`, `NBB-704A`, `NBB-704B`, `NBB-706` |

## Finding Mapping

| Finding | New owner |
|---|---|
| Tool/prompt asset moves unsafe with path-based loaders | `NBB-207A`, `NBB-207B`, `NBB-207C` |
| `data_services/` is domain CRUD, not a data layer | `NBB-209A` through `NBB-209E` |
| Missing route/domain surfaces: prompts, Google, transcription | `NBB-104`, `NBB-209A` through `NBB-209E`, `NBB-601` |
| Chat tool ownership ambiguous | `NBB-303` |
| `shared/` and `base/` loopholes | `NBB-104`, `NBB-704A`, `NBB-704B` |
| Deep research unassigned | `NBB-403` |
| Platform/provider file adapter target conflicts with audit | `NBB-206`, `NBB-401`, `NBB-705B`, `NBB-705C`, `NBB-705D` |
| Frontend auth/hook ownership unclear | `NBB-108A`, `NBB-602`, `NBB-603` |
| Correctness/tooling preflight missing | `NBB-103`, `NBB-106`, `NBB-107`, `NBB-109` |
| `utils/` empty contradicts approved exceptions | `NBB-705E` |
| Executor/tool-run pair invariant missing | `NBB-502`, `NBB-403` |
| Chat naming collision risk | `NBB-304` |
| Service suffix dropping/stateless conversion/barrel cleanup missing | `NBB-706` |
| Codemod, AST verifier, pyright, CI missing | `NBB-103`, `NBB-704A`, `NBB-704B` |
| Sub-buckets not frozen | `NBB-103` |
| Auth middleware target ambiguity | `NBB-201` |
| Cross-stack citation and source contracts omitted | `NBB-205`, `NBB-301`, `NBB-402` |
| API route layer silently stays old shape | `NBB-104`, `DEFERRED.md` |
| Supabase migrations/RLS/storage has no owner | `NBB-204` |
| Studio jobs are a third layer | `NBB-502`, `NBB-703` |
| Prompt/tool JSON assets not colocated | `NBB-207A`, `NBB-207B`, `NBB-207C` |
| Flask app factory touchpoint unnamed | `NBB-208A`, `NBB-201` |
| No CI | `NBB-103` |
| Test safety net too thin | `NBB-106`, `NBB-107`, `NBB-701`, `NBB-702`, `NBB-703` |
| No dependency-direction rules | `NBB-104`, `NBB-206`, `NBB-704A`, `NBB-704B` |
| Deferred work has no home | `DEFERRED.md` |
| Naming convention drift | `NBB-501A`, `NBB-501B`, `NBB-706` |
| Frontend too small in old backlog | `NBB-105`, `NBB-108A`, `NBB-108B`, `NBB-601`, `NBB-602`, `NBB-603`, `NBB-604` |
| Background subsystem missing | `NBB-210`, `NBB-703` |
| MCP/connectors as extension points flattened | `NBB-202B`, `NBB-303`, `NBB-403`, `NBB-603` |
| Runtime `.env` reload and config fragility | `NBB-208A` |
| Observability/logging owner missing | `NBB-208B` |
| Unsafe CSV analysis too late | `NBB-203`, `DEFERRED.md` `D-002` |
| Repo docs contradict proposed architecture | `NBB-102` |
| Branch/repo instructions stale | `NBB-101` |
| Permissions fail open | `NBB-202A`, `NBB-107` |
| Platform/providers migration too large and blocking | `NBB-206`; bulk provider/connector migration is intentionally not a gate |
| Studio taxonomy needs decision before migration | `NBB-501A`, `NBB-501B`, `NBB-503` |
| Route smokes/auth tests too late | `NBB-106`, `NBB-107` |
| Frontend tests omitted | `NBB-108A`, `NBB-108B`, `DEFERRED.md` |
| Agent execution log ownership missing | `NBB-210` |
| Taste-audit Phase 1 correctness fixes missing | `NBB-109` |
| Permanent raw-code analysis replacement is out of active graph | `DEFERRED.md` `D-002` |

## Deferred Mapping

| Deferred item | Register |
|---|---|
| Route movement out of `backend/app/api` | `DEFERRED.md` |
| Permanent raw-code analysis replacement | `DEFERRED.md` `D-002` |
| Broad security review beyond raw-code analysis and permissions | `DEFERRED.md` |
| Full frontend test expansion beyond baseline smoke tests | `DEFERRED.md` if `NBB-108A` defers it |
