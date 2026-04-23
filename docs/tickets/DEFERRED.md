# Deferred Work Register

This register prevents known risks from disappearing while keeping the structure migration bounded.

## D-001 - Move route modules into domains

**Status:** Deferred.

**Reason:** This migration declares `backend/app/api` as transport-only and keeps route files in place to reduce churn. Moving route modules into domain packages is a separate API-boundary redesign.

**Current policy:** Route modules may parse HTTP, run guards, call domain public surfaces, and format responses. They must not own product behavior.

**Suggested owner:** Future API/domain-boundary epic.

## D-002 - Permanent raw-code analysis replacement if `NBB-404` is not completed in this program

**Status:** Deferred only after `NBB-203` mitigation is live.

**Reason:** `NBB-203` disables or flags off raw-code analysis outside explicit dev/single-user mode before migration. The permanent solution is declarative analysis or a real sandbox in `NBB-404`.

**Guardrail:** Do not move source-analysis code before `NBB-203` lands.

**Suggested owner:** Sources/security owner.

## D-003 - Broad security review beyond permissions and raw-code analysis

**Status:** Deferred.

**Reason:** This backlog fixes the obvious permission and raw-code execution risks, but does not attempt a full security audit.

**Scope to revisit:**
- service-role Supabase access patterns
- media/query-token routes
- generated asset access
- integration secret exposure
- MCP and external connector trust boundaries

**Suggested owner:** Security/platform owner.

## D-004 - Full frontend test expansion if `NBB-108` chooses deferral

**Status:** Conditional.

**Reason:** `NBB-108` must either add baseline frontend ownership/render smoke tests or explicitly defer them here.

**Minimum follow-up if deferred:**
- app render smoke
- chat/sources/studio shell render smoke
- permission-provider behavior smoke
- citation UI contract smoke

**Suggested owner:** Frontend owner.

## D-005 - Cross-stack contract redesign beyond preservation

**Status:** Deferred.

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

**Suggested owner:** Contract/API owner.
