# Ticket Traceability

This file preserves the review trail after the flat `NBB-001` through `NBB-018` tickets were archived under `docs/tickets/archive/legacy-flat/`.

Note: in this worktree `docs/tickets/` is currently untracked, so the archive was created as a filesystem move rather than a git-tracked rename. There is no prior committed file history for `git log --follow` to preserve here.

## Legacy Flat Ticket Mapping

| Legacy flat ticket | New owner |
|---|---|
| `NBB-001` Freeze legacy buckets | `NBB-101`, `NBB-102`, `NBB-103`, `NBB-104`, `NBB-105` |
| `NBB-002` Create backend target packages | `NBB-104`, `NBB-206` |
| `NBB-003` Auth consolidation | `NBB-201`, `NBB-202` |
| `NBB-004` Platform extraction | `NBB-206`, `NBB-208`, `NBB-401`, `NBB-705` |
| `NBB-005` Chat migration | `NBB-301`, `NBB-302`, `NBB-303`, `NBB-304` |
| `NBB-006` Sources migration | `NBB-401`, `NBB-402`, `NBB-702` |
| `NBB-007` Structured analysis | `NBB-203`, `NBB-403`, `NBB-404` |
| `NBB-008` Studio skeleton | `NBB-501`, `NBB-502` |
| `NBB-009` Studio blog pilot | `NBB-503` |
| `NBB-010` Studio documents | `NBB-504` |
| `NBB-011` Studio marketing | `NBB-505` |
| `NBB-012` Studio design/logo | `NBB-506` |
| `NBB-013` Studio learning/media | `NBB-507` |
| `NBB-014` Smaller domains | `NBB-209`, `NBB-601`, `NBB-603` |
| `NBB-015` Utils cleanup | `NBB-705` |
| `NBB-016` Frontend shells | `NBB-105`, `NBB-601`, `NBB-602` |
| `NBB-017` Frontend lib/contexts | `NBB-603`, `NBB-604` |
| `NBB-018` Tests/shims/delete legacy | `NBB-103`, `NBB-701`, `NBB-702`, `NBB-703`, `NBB-704`, `NBB-706` |

## Finding Mapping

| Finding | New owner |
|---|---|
| Tool/prompt asset moves unsafe with path-based loaders | `NBB-207` |
| `data_services/` is domain CRUD, not a data layer | `NBB-209` |
| Missing route/domain surfaces: prompts, Google, transcription | `NBB-104`, `NBB-209`, `NBB-601` |
| Chat tool ownership ambiguous | `NBB-303` |
| `shared/` and `base/` loopholes | `NBB-104`, `NBB-704` |
| Deep research unassigned | `NBB-403` |
| Platform file adapter target conflicts with audit | `NBB-206`, `NBB-401`, `NBB-705` |
| Frontend auth/hook ownership unclear | `NBB-602`, `NBB-603` |
| Correctness/tooling preflight missing | `NBB-103`, `NBB-106`, `NBB-107` |
| `utils/` empty contradicts approved exceptions | `NBB-705` |
| Executor/tool-run pair invariant missing | `NBB-502`, `NBB-403` |
| Chat naming collision risk | `NBB-304` |
| Service suffix dropping/stateless conversion/barrel cleanup missing | `NBB-706` |
| Codemod, AST verifier, pyright, CI missing | `NBB-103`, `NBB-704` |
| Sub-buckets not frozen | `NBB-103` |
| Auth middleware target ambiguity | `NBB-201` |
| Cross-stack citation and source contracts omitted | `NBB-205`, `NBB-301`, `NBB-402` |
| API route layer silently stays old shape | `NBB-104`, `DEFERRED.md` |
| Supabase migrations/RLS/storage has no owner | `NBB-204` |
| Studio jobs are a third layer | `NBB-502`, `NBB-703` |
| Prompt/tool JSON assets not colocated | `NBB-207` |
| Flask app factory touchpoint unnamed | `NBB-208`, `NBB-201` |
| No CI | `NBB-103` |
| Test safety net too thin | `NBB-106`, `NBB-107`, `NBB-701`, `NBB-702`, `NBB-703` |
| No dependency-direction rules | `NBB-104`, `NBB-206`, `NBB-704` |
| Deferred work has no home | `DEFERRED.md` |
| Naming convention drift | `NBB-501`, `NBB-706` |
| Frontend too small in old backlog | `NBB-105`, `NBB-108`, `NBB-601`, `NBB-602`, `NBB-603`, `NBB-604` |
| Background subsystem missing | `NBB-210`, `NBB-703` |
| MCP/connectors as extension points flattened | `NBB-303`, `NBB-403`, `NBB-603` |
| Runtime `.env` reload and config fragility | `NBB-208` |
| Observability/logging owner missing | `NBB-208` |
| Unsafe CSV analysis too late | `NBB-203`, `NBB-404` |
| Repo docs contradict proposed architecture | `NBB-102` |
| Branch/repo instructions stale | `NBB-101` |
| Permissions fail open | `NBB-202`, `NBB-107` |
| Platform migration too large and blocking | `NBB-206`; bulk adapter migration is intentionally not a gate |
| Studio taxonomy needs decision before migration | `NBB-501`, `NBB-503` |
| Route smokes/auth tests too late | `NBB-106`, `NBB-107` |
| Frontend tests omitted | `NBB-108`, `DEFERRED.md` |

## Deferred Mapping

| Deferred item | Register |
|---|---|
| Route movement out of `backend/app/api` | `DEFERRED.md` |
| Permanent raw-code analysis replacement if not delivered in `NBB-404` during this program | `DEFERRED.md` |
| Broad security review beyond raw-code analysis and permissions | `DEFERRED.md` |
| Full frontend test expansion beyond baseline smoke tests | `DEFERRED.md` if `NBB-108` defers it |
