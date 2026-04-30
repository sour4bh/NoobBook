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

**Status:** Resolved by `NBB-910` through `NBB-915`; reconciled by `NBB-918`

**Resolution:** The broad parked security item has been split into concrete
hardening tickets and closed for the risks known at migration time:

- `NBB-910` splits public signup ownership from global admin bootstrap. Public
  signup creates a normal user in the current tree. Workspace-owner signup is
  only valid after a workspace-scoped membership model exists; it must never
  imply global admin.
- `NBB-911` replaces primary JWT browser asset URLs with scoped asset access.
- `NBB-912` adds ownership to background tasks and hardens service-role reads.
- `NBB-913` completes provider and connector permission gates for Google Drive,
  ElevenLabs, and MCP.
- `NBB-914` reconciles Supabase storage paths, policies, and generated asset
  isolation.
- `NBB-915` hardens Google OAuth production redirects and replay resistance.

**Residual scope:** None kept in this deferred register. Future broad security
reviews are normal security backlog work, not hidden migration debt.

## D-004 - Full frontend test expansion

**Status:** Resolved by `NBB-908`

**Resolution:** `NBB-908` adds the frontend Vitest/jsdom/React Testing Library
smoke harness that `NBB-108A` deferred, including app shell, permission
provider, workspace shell, and citation UI coverage.

## D-005 - Cross-stack contract redesign beyond preservation

**Status:** Resolved by `NBB-010`; reconciled by `NBB-1008`

**Resolution:** `NBB-205` named and preserved the migration-time wire
contracts. `NBB-916` and `NBB-917` converted the highest-risk preserved
contracts into backend-owned DTOs and frontend runtime parsers:

- `NBB-916` defines backend-owned DTOs for API envelopes, auth/session,
  chat streaming events, citations, background-task polling, project costs,
  source file metadata, studio jobs/events, generated asset access, scoped
  asset-token payloads, and relevant JSONB payloads.
- `NBB-917` adds frontend Zod parsers for the frontend-facing DTOs and makes
  chat SSE share the same auth refresh/retry lifecycle as normal API calls.

**Final workspace resolution:** `NBB-010` implements the collaborative
workspace/team membership contract. Public signup creates a personal workspace
where the user is workspace `owner` and global `user`; users join additional
workspaces through signed one-time invites; projects are private by default and
visible only through explicit `project_members` rows; workspace roles
(`owner`, `admin`, `member`) govern team/settings/secret management; project
roles (`owner`, `editor`, `viewer`) govern private project access and mutation;
global admin remains an instance/bootstrap-only role, not a normal team owner.
Workspace-scoped settings/secrets and frontend workspace/project sharing flows
land in the same epic, so no residual cross-stack redesign scope remains in
this deferred register.

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

**Status:** Resolved by `NBB-905` and completed for collaborative membership by
`NBB-010`

**Resolution:** `verify_project_access()` now uses a pure project-access check,
`GET /projects/{id}` is side-effect-free, and `POST /projects/{id}/open` is the
only route that updates `last_accessed`.

**Workspace completion:** `NBB-010` extends the pure access check into explicit
private project membership roles, so the earlier owner-only residual is closed.

## D-009 - Connector pagination completeness

**Status:** Backlog

**Context:** Jira and Notion connector clients currently return bounded first
pages for some read operations. This is acceptable for the NBB-011 runtime
migration because the issue is connector completeness, not a provider/runtime
contract blocker.

**Scope:** Add explicit pagination support for:

- Jira issue search beyond the first `max_results <= 100` page in
  `backend/app/connectors/jira/client.py`.
- Notion workspace search using `has_more` / `start_cursor` in
  `backend/app/connectors/notion/client.py`.
- Notion page block reads using `has_more` / `next_cursor` for pages with more
  than 100 top-level blocks.

**Expected shape:** Keep pagination policy at the connector boundary. Do not
silently fetch unbounded result sets; expose cursor/limit metadata or apply a
clear bounded loop with tests so callers understand truncation and cost.
