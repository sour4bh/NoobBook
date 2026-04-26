# Deferred Work Register

This register prevents known risks from disappearing while keeping the structure migration bounded.

## D-001 - Move route modules into domains

**Status:** Deferred

**Reason:** This migration declares `backend/app/api` as transport-only and keeps route files in place to reduce churn. Moving route modules into domain packages is a separate API-boundary redesign.

**Current policy:** Route modules may parse HTTP, run guards, call domain public surfaces, and format responses. They must not own product behavior.

**Suggested owner:** Future API/domain-boundary epic.

## D-002 - Permanent raw-code analysis replacement

**Status:** Deferred
**Unblocks when:** `NBB-203` mitigation is live.

**Reason:** `NBB-203` disables or flags off raw-code analysis unless both `NOOBBOOK_AUTH_REQUIRED=false` and `NOOBBOOK_ALLOW_RAW_ANALYSIS=true` before migration. The permanent solution is declarative analysis or a real sandbox, but that replacement is intentionally out of the active migration graph.

**Guardrail:** Do not move source-analysis code before `NBB-203` lands.

Production analysis remains disabled. No ticket may re-enable CSV/database-style model-generated code execution in auth-required mode until `D-002` is completed.

**Suggested owner:** Sources/security owner.

## D-003 - Broad security review beyond permissions and raw-code analysis

**Status:** Deferred

**Reason:** This backlog fixes the obvious permission and raw-code execution risks, but does not attempt a full security audit.

**Scope to revisit:**
- service-role Supabase access patterns
- media/query-token routes
- generated asset access
- connector secret exposure
- MCP and external connector trust boundaries

**Suggested owner:** Security/providers/connectors owner.

## D-004 - Full frontend test expansion (deferred by `NBB-108A`)

**Status:** Deferred
**Decision:** `NBB-108A` chose deferral on 2026-04-24. Baseline frontend ownership/render smoke tests will not ship as part of this migration sprint. `NBB-108B` remains in the backlog at P1 as the follow-up implementation ticket and is the re-entry point when the frontend owner picks this up.

**Reason:** The sprint is backend-structure-heavy. Adding a frontend test toolchain (test runner selection, config wiring, CI extension, mock/jsdom setup) during migration adds surface area and tooling risk for no movement-safety win — frontend moves in Epic 006 (`NBB-602`, `NBB-603`, `NBB-604`) are guarded by the existing `npm run build` in CI plus backend route/contract tests from `NBB-106`, `NBB-107`, and `NBB-205`. Frontend shells (`NBB-105`, `NBB-601`) are docs-only and do not change runtime behavior that a smoke test would catch. No shim or forwarding module in `NBB-706` depends on a frontend test pass.

**Risk accepted:** Shell render regressions and permission-provider wiring bugs may reach `develop` during frontend moves without automated catch. Mitigation: reviewers manually smoke the running app (`bin/dev`) for app boot, chat/sources/studio shell mount, and permission-provider state during review of `NBB-602`/`NBB-603`/`NBB-604`.

**Minimum follow-up when `NBB-108B` is picked up:**
- app render smoke
- chat/sources/studio shell render smoke
- permission-provider behavior smoke
- citation UI contract smoke

Concrete command and CI placement are deferred to `NBB-108B`; Vitest plus React Testing Library is the expected baseline but is not locked here.

**Suggested owner:** Frontend owner (accepts the risk above until `NBB-108B` lands).

## D-005 - Cross-stack contract redesign beyond preservation

**Status:** Deferred

**Reason:** `NBB-205` names and preserves current contracts so migration can proceed. Redesigning those contracts is larger than this structure rewrite.

**Contracts covered for preservation:**
- chat streaming event format
- citation marker and lookup format
- chat tool invocation/result wire format
- `studio_signals`/studio event shape
- `projects.costs` JSONB shape
- `messages.content` JSONB shape
- background-task polling response
- tool-schema JSON contract
- source kind/MIME/status contract
- studio job status/progress/result contract
- permissions JSON contract
- auth/session response contract
- authenticated media/generated-asset access contract
- query-token asset access contract

**Suggested owner:** Contract/API owner.

## D-006 - OAuth callback auth bypass

**Status:** Deferred

**Reason:** The API-wide `before_request` guard currently skips `/api/v1/auth/*` and `/api/v1/health`, but OAuth providers redirect into routes such as `/api/v1/google/callback`. Those callbacks cannot attach the app's bearer token header and should be validated by their own OAuth `state`/provider-token flow instead of the generic API JWT guard.

**Suggested owner:** Auth/connectors owner.

## D-007 - Dev-mode API middleware fallback

**Status:** Deferred

**Reason:** `NOOBBOOK_AUTH_REQUIRED=false` promotes a fallback identity in the domain auth layer, but the API blueprint middleware still calls `validate_token()` directly and returns 401 when no bearer token is present. Local single-user/dev mode therefore remains stricter at the transport boundary than the domain policy advertises.

**Suggested owner:** Auth/API owner.

## D-008 - Project membership access check

**Status:** Deferred

**Reason:** `NBB-201` consolidated project-access checks, but the canonical `verify_project_access()` path still calls `project_service.get_project(project_id, user_id=...)`, which both performs an owner-only lookup and mutates `last_accessed`. The follow-up should separate "can this user access the project?" from "load and mark this project opened", and should use the collaborative membership path when team access is re-enabled.

**Suggested owner:** Auth/projects owner.
