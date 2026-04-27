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

1. **Root registry and retired-root no-return.** Every tracked top-level child of
   `backend/app/` must be a canonical backend root from `STRUCTURE.md`'s
   NBB-104/NBB-902 table. `config/` is canonical runtime configuration.
   `services/` is retired by NBB-811; `utils/` and `data/prompts/` are
   retired by NBB-812.
   Any tracked file under those retired roots, any forbidden `app.services.*`
   or forbidden `app.utils.*` reference in backend app code or tests, or
   current docs that present retired roots as live architecture fail the check.
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
   `app.chat.loop` is rejected.
5. **Independent roots stay independent.** `auth/`, `projects/`,
   `connectors/`, `brand/`, `background/`, and `settings/` may not import
   from `app.chat`, `app.sources`, or `app.studio`. The empirically-zero
   state at base commit `f118268` is the regression guard. One inherited
   exception is allowlisted: `auth/tool_policy.py` lazily registers
   sources-owned tool capabilities (NBB-202B cross-cutting registry).
6. **API is transport-only.** App code outside `backend/app/api/` must not
   import `app.api.*` route modules. The app factory is the only non-route
   exception because it registers the root blueprint.

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

## Type and AST safety checks (NBB-704C)

Three additional CI guardrails ship with NBB-704C:

- `pnpm dlx pyright@1.1.409 --project pyrightconfig.json` — pyright
  type-checking on `backend/app/`. Pinned at version 1.1.409 (do not float
  to `@latest`); pyright is intentionally not added to
  `backend/requirements.txt`.
- `python backend/scripts/verify_project_id_coverage.py` — every call to
  `claude_service.send_message` (or `stream_message`) must pass a
  `project_id`. Owned by NBB-109; wired to CI by NBB-704C.
- `python backend/scripts/verify_no_stateless_singletons.py` — flags new
  module-level `class *Service` or `class *Executor` definitions whose
  `__init__` is empty when the same module assigns a singleton instance.
  Ten baseline candidates at `f3281a7` are allowlisted as `(rel_path,
  class_name)` pairs in the script — two are NBB-706 conversion targets
  (`EmbeddingService`, `VideoPromptService`); eight are orchestration
  classes from NBB-706's "Keep-as-class" list. New occurrences fire the
  rule.

### pyright config rationale

`pyrightconfig.json` lives at the repo root. Two structural decisions are
load-bearing and worth recording outside the JSON file (since
`pyrightconfig.json` does not parse JSONC comments reliably in pyright
1.1.409):

1. **Strict block narrowing.** The dispatch's seven seeded strict paths
   (`chat/tools`, `chat/loop.py`, `sources/analysis`, `studio/**/tool.py`,
   `studio/**/run.py`, `connectors`, `providers`) reproduce 933 strict-mode
   errors at `f3281a7`, dominated by `reportUnknownMemberType` /
   `reportUnknownVariableType` migration-code noise. Pyright 1.1.409 forces
   strict-mode rule severities to error regardless of root-level
   `reportXxx` overrides, so config-level tuning cannot soften strict
   paths. The strict block is narrowed to `backend/app/chat/tools.py`
   only — the chat-owned tool registry public surface, where future
   tool-schema additions land. The remaining paths fall back to standard
   mode with the per-rule severity tuning below.
2. **Per-rule severity tuning** (standard mode only). The dispatch
   authorizes specific `reportXxx` rule tuning at the config level. The
   following rules are downgraded to `warning` for the standard `include`
   block (`backend/app`):
   - `reportUnknownMemberType`, `reportUnknownVariableType`,
     `reportUnknownArgumentType`, `reportUnknownParameterType`,
     `reportMissingTypeArgument`, `reportUnknownLambdaType` —
     migration-code Unknown-type noise. Type-hint pass is owned by NBB-104
     follow-ups, not NBB-704C.
   - `reportArgumentType`, `reportReturnType`, `reportCallIssue`,
     `reportAttributeAccessIssue`, `reportOptionalMemberAccess`,
     `reportOptionalSubscript`, `reportOptionalCall`,
     `reportOptionalIterable`, `reportOptionalOperand`,
     `reportOperatorIssue`, `reportGeneralTypeIssues`,
     `reportPossiblyUnboundVariable`, `reportAssignmentType` — real
     type-bug noise in migration code; NBB-704C is verification-only with
     zero edits to `backend/app/`. Behavior-bearing fixes belong to
     post-NBB-706 cleanup tickets.

   Strict-tier rules NOT downgraded (`reportUnusedVariable`,
   `reportUnusedImport`, `reportUnnecessaryIsInstance`,
   `reportDeprecated`, `reportUnsupportedDunderAll`, etc.) keep error-tier
   on the standard block.

The result is `0 errors, 4640 warnings` on pyright 1.1.409 against
`backend/app/` at `f3281a7`. CI runs the pinned pyright command and fails
on non-zero exit; warnings are visible but not blocking.
