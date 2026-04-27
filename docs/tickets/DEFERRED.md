# Deferred Work Register

This register prevents known risks from disappearing while keeping the
structure migration bounded.

## D-001 - Move route modules into domains

**Status:** Resolved by `NBB-906`

**Resolution:** Route files stay under `backend/app/api` by explicit design.
`NBB-906` closes this item by making `api/` the HTTP transport boundary:
routes may parse HTTP, run guards, call public domain surfaces, and format
responses only. `verify_architecture.py` now rejects non-transport app code
that imports `app.api.*` route modules.

## D-002 - Permanent raw-code analysis replacement

**Status:** Resolved by `NBB-907`

**Resolution:** CSV analysis no longer executes model-written Python. The
`run_analysis` tool is now a Pydantic-validated declarative operation engine
covering inspect, filter, aggregate, sort/limit, and chart operations.
`NOOBBOOK_ALLOW_RAW_ANALYSIS` is no longer required for CSV analysis, and
invalid operations fail closed.

## D-003 - Broad security review beyond permissions and raw-code analysis

**Status:** Deferred by explicit decision

**Reason:** `NBB-009` fixes selected known security-adjacent defects, but it is
not a full security audit.

**Scope to revisit:**
- service-role Supabase access patterns
- media/query-token routes
- generated asset access
- connector secret exposure
- MCP and external connector trust boundaries
- OAuth state replay hardening beyond signed short-lived state

**Suggested owner:** Security/providers/connectors owner.

## D-004 - Full frontend test expansion

**Status:** Resolved by `NBB-908`

**Resolution:** `NBB-908` adds the frontend Vitest/jsdom/React Testing Library
smoke harness that `NBB-108A` deferred, including app shell, permission
provider, workspace shell, and citation UI coverage.

## D-005 - Cross-stack contract redesign beyond preservation

**Status:** Deferred by explicit decision

**Reason:** `NBB-205` named and preserved current contracts so migration could
proceed. `NBB-009` keeps those contracts stable while closing runtime/auth and
analysis defects. Redesigning contracts remains a separate API/frontend product
decision.

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

**Status:** Resolved by `NBB-904`

**Resolution:** `/api/v1/google/callback` bypasses the generic bearer-token
guard and validates an opaque signed OAuth `state` before token exchange.
Missing, invalid, or expired state is rejected before any provider callback
handling runs.

## D-007 - Dev-mode API middleware fallback

**Status:** Resolved by `NBB-903`

**Resolution:** The API blueprint middleware now uses `app.auth.identity` as the
source of truth. When `NOOBBOOK_AUTH_REQUIRED=false`, it sets `g.user_id` to the
resolved fallback identity and lets protected routes proceed without a bearer
token.

## D-008 - Project membership access check

**Status:** Resolved for owner-only semantics by `NBB-905`; team membership
redesign remains part of `D-005`

**Resolution:** `verify_project_access()` now uses a pure project-access check,
`GET /projects/{id}` is side-effect-free, and `POST /projects/{id}/open` is the
only route that updates `last_accessed`.

**Follow-up boundary:** Broader collaborative membership semantics are a
cross-stack contract/product redesign and remain under `D-005`.
