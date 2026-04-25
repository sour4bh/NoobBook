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
- `backend/scripts/verify_architecture.py` (NBB-704A + NBB-704B) — stdlib-only
  static checks that enforce the NBB-104 root list, the NBB-206
  providers/connectors boundary at the external edge, and post-migration
  cross-domain rules.

`verify_architecture.py` enforces five rules:

1. **Root registry.** Every top-level child of `backend/app/` must be a
   canonical backend root from `STRUCTURE.md`'s NBB-104 table. Existing
   legacy roots (`services/`, `utils/`) and the `config/` package are
   tolerated as known migration state. A new root outside the approved list
   fails the check. A new mechanism bucket such as `backend/app/agents/` is
   exactly the regression this catches.
2. **`providers/` is a leaf.** Modules under `backend/app/providers/` must
   not import from `app.api`, `app.connectors`, or any domain root (`auth`,
   `projects`, `chat`, `sources`, `studio`, `brand`, `background`,
   `settings`). Five inherited Anthropic-cost/token imports are documented
   in `backend/app/providers/CHARTER.md` "Documented exceptions (NBB-704B)"
   and allowlisted in the script as `(path, lineno, target_root)` tuples.
3. **`connectors/` stays at the external edge.** Modules under
   `backend/app/connectors/` may import from `app.providers`, `app.auth`,
   and `app.projects` (per `connectors/CHARTER.md`). Imports from `app.api`
   or any other domain root fail the check.
4. **Chat publics-only.** Code outside `backend/app/chat/` must reach chat
   through the public surface declared in `app.chat.__all__` (`store`,
   `tools`, `schemas`, `send`, `stream`, `ChatEvent`, `ChatResponse`).
   Reaching deeper paths such as `app.chat.message.store` or
   `app.chat.loop` is rejected. Inherited consumers of
   `app.chat.message.store.message_service` are allowlisted in the script
   as `(importer_path, target_module)` pairs awaiting the NBB-706 cleanup
   pass that re-exports `message_service` from `app.chat.store`.
5. **Independent roots stay independent.** `auth/`, `projects/`,
   `connectors/`, `brand/`, `background/`, and `settings/` may not import
   from `app.chat`, `app.sources`, or `app.studio`. The empirically-zero
   state at base commit `f118268` is the regression guard. One inherited
   exception is allowlisted: `auth/tool_policy.py` lazily registers
   sources-owned tool capabilities (NBB-202B cross-cutting registry).

Relative imports inside any package are not checked; they stay within the
package by construction.

The sources/studio public-surface enforcement and the frontend ownership
check are intentionally deferred from NBB-704B. Sources/studio expose
per-item layer paths through `LAYER_MAP.md` and the sources `CHARTER.md`
decision map (95+ public submodule paths), too verbose to encode here
without authoring a heavier framework. The frontend ownership check waits
for a frontend script home; no `frontend/scripts/` tree exists today.
Both gaps are tracked as follow-ups against the NBB-706 final cleanup
pass.

Type checks and AST safety (stateless-singleton prevention, project_id
coverage) are owned by NBB-704C.
