# Backend structure reference

Structure rules live in the repo-root [`STRUCTURE.md`](../STRUCTURE.md). That
file owns the Canonical Backend Roots table (NBB-104), the Frozen Destinations
list, the Placement Checklist, and the providers/connectors boundary
(NBB-206). Read it before adding or moving any backend file.

Per-root charters live next to each root:

- `backend/app/background/CHARTER.md`
- `backend/app/brand/CHARTER.md`
- `backend/app/chat/CHARTER.md`
- `backend/app/connectors/CHARTER.md`
- `backend/app/projects/CHARTER.md`
- `backend/app/providers/CHARTER.md`
- `backend/app/sources/CHARTER.md`
- `backend/app/studio/CHARTER.md`

Storage contracts live under [`supabase/STORAGE_CONTRACTS.md`](supabase/STORAGE_CONTRACTS.md)
and [`supabase/migrations/OWNERS.md`](supabase/migrations/OWNERS.md) (NBB-204).

## Architecture checks

Two CI guardrails run on every push/PR:

- `scripts/ci/check_no_new_legacy_files.py` (NBB-103) — blocks new files under
  the frozen destinations named in the repo-root `STRUCTURE.md`.
- `backend/scripts/verify_architecture.py` (NBB-704A) — early, stdlib-only
  static checks that enforce the NBB-104 root list and the NBB-206
  providers/connectors boundary at the external edge.

`verify_architecture.py` enforces exactly three rules:

1. **Root registry.** Every top-level child of `backend/app/` must be a
   canonical backend root from `STRUCTURE.md`'s NBB-104 table. Existing
   legacy roots (`services/`, `utils/`) and the `config/` package are
   tolerated as known migration state. A new root outside the approved list
   fails the check. A new mechanism bucket such as `backend/app/agents/` is
   exactly the regression this catches.
2. **`providers/` is a leaf.** Modules under `backend/app/providers/` must
   not import from `app.api`, `app.connectors`, or any domain root (`auth`,
   `projects`, `chat`, `sources`, `studio`, `brand`, `background`,
   `settings`).
3. **`connectors/` stays at the external edge.** Modules under
   `backend/app/connectors/` may import from `app.providers`, `app.auth`,
   and `app.projects` (per `connectors/CHARTER.md`). Imports from `app.api`
   or any other domain root fail the check. Distinguishing a domain's
   public surface from its internals is out of scope for NBB-704A — that is
   NBB-704B's job.

Relative imports inside either package are not checked; they stay within the
package by construction.

Richer post-migration import-boundary coverage is owned by NBB-704B. Type
checks and AST safety (stateless-singleton prevention, project_id coverage)
are owned by NBB-704C.
