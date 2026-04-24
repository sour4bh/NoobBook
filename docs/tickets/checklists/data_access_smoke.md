# Cross-user data access smoke checklist

**Owner (NBB-204):** Backend data-contracts lane owns this inventory. Test implementation belongs to downstream tickets: auth/permissions (`NBB-107`), sources/citations (`NBB-702`), studio jobs and background status (`NBB-703`). `NBB-204` does not implement the tests.

**Validation approach:** every row below lists (a) the cross-user attempt, (b) the expected response, (c) the guard that should reject it. Tests in the owning ticket must assert against the stated guard, not merely against the response code — if the backend project guard is bypassed but the hosted-mode RLS still rejects the request, that is a regression that would pass a response-code-only assertion.

**Cross-reference:** `backend/supabase/migrations/OWNERS.md` (table access model), `backend/supabase/STORAGE_CONTRACTS.md` (bucket guards).

## Deployment-mode matrix (run each row against both modes)

| Mode | RLS active? | Storage policy | Primary guard |
|---|---|---|---|
| Supabase-hosted | Yes (migrations 00003, 00006, 00007, 00010) | `auth.uid()`-based policies from 00002 | RLS + backend project guard (defence-in-depth) |
| Self-hosted Docker | No (init.sql does not `ENABLE ROW LEVEL SECURITY` on core tables) | `Allow all on <bucket>` (init.sql) | Backend project guard is the only barrier |

Every checklist row must pass in **both** modes. If a test has to skip one mode, state the reason inline.

## 1. Projects

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 1.1 | User A requests `GET /api/v1/projects/{A-project-id}` as user B | 404 | `@before_request` -> `project_service.has_project_access(project_id, user_id)` in `backend/app/__init__.py`. Hosted mode adds `projects` RLS. |
| 1.2 | User B sends `PUT /api/v1/projects/{A-project-id}` with a benign body as B | 404 | Same as 1.1. |
| 1.3 | User B sends `DELETE /api/v1/projects/{A-project-id}` as B | 404 | Same as 1.1. |
| 1.4 | User B lists projects (`GET /api/v1/projects`) | Response must not contain user A's project rows | Project list query filters by authenticated identity; do not assert on response body only, assert that the query returned zero A-owned rows. |

## 2. Sources

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 2.1 | User B requests `GET /api/v1/projects/{A-project-id}/sources` as B | 404 | Project guard. |
| 2.2 | User B requests `GET /api/v1/projects/{A-project-id}/sources/{A-source-id}` as B | 404 | Project guard. |
| 2.3 | User B requests `GET /api/v1/projects/{A-project-id}/sources/{A-source-id}/download` as B | 404 (must **not** redirect to a signed URL) | Project guard. `backend/app/api/sources/routes.py::download_source` calls the source lookup first; in hosted mode the RLS on `sources` also rejects the metadata read. |
| 2.4 | User B posts `POST /api/v1/projects/{A-project-id}/sources` (file upload) as B | 404 | Project guard. The upload handler must reject before touching `raw-files`. |
| 2.5 | User B requests `POST /api/v1/projects/{A-project-id}/sources/{A-source-id}/cancel` or `.../retry` as B | 404 | Project guard. |
| 2.6 | User B issues a direct signed-URL request against the `raw-files` bucket for object `{A-project-id}/{A-source-id}/{filename}` (hosted mode only) | Fail (signed URL cannot be obtained without service role) | Hosted-mode storage policies + backend not issuing signed URLs to B. **Note:** runtime paths do not satisfy the `auth.uid()` first-folder rule today, so storage RLS alone is advisory — see "Known inconsistency" in `STORAGE_CONTRACTS.md`. |

## 3. Chunks and citations

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 3.1 | User B requests `GET /api/v1/projects/{A-project-id}/citations/{A-chunk-id}` as B | 404 | Project guard on the route prefix. Hosted mode: `chunks` RLS via `source -> project`. |
| 3.2 | User B invokes the chat `search_sources` tool with `source_id` belonging to user A (via their own chat context) | Tool returns zero results (not an error leaking A's content) | The search executor must filter by the chat's `project_id`. Test from within the chat loop, not directly against the tool executor. |
| 3.3 | User B requests chunk bytes for an object path containing user A's `{project_id}/{source_id}` via any chunk-serving helper | 404 / not found | Project guard. `chunks` bucket has no user-scoped serving route today. |

## 4. Chats and messages

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 4.1 | User B requests `GET /api/v1/projects/{A-project-id}/chats` as B | 404 | Project guard. Hosted mode: `chats` RLS via `project`. |
| 4.2 | User B requests `GET /api/v1/projects/{A-project-id}/chats/{A-chat-id}` as B | 404 | Same as 4.1. |
| 4.3 | User B posts `POST /api/v1/projects/{A-project-id}/chats/{A-chat-id}/messages` as B | 404 | Project guard. Hosted mode: `messages` RLS via `chat -> project`. |
| 4.4 | User B sets `selected_source_ids` on A's chat by crafting the request path | 404 | Project guard. |
| 4.5 | User B polls `/api/v1/projects/{A-project-id}/costs` or `/prompt` or `/memory` as B | 404 | Project guard. |

## 5. Studio outputs

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 5.1 | User B requests `GET /api/v1/projects/{A-project-id}/studio/<any-category>/...` as B | 404 | Project guard. `studio_signals` has RLS (hosted); `studio_jobs` has **no RLS** — the project guard is the only barrier. |
| 5.2 | User B creates a studio job against user A's project (`POST` on any studio category) as B | 404 | Project guard. |
| 5.3 | User B polls for A's studio output signed URL via any studio route as B | 404 (must **not** return a signed URL) | Project guard. The signed URL generator in `storage_service` must be called only from inside a project-guarded route. |
| 5.4 | User B issues a direct signed-URL request against the `studio-outputs` bucket for `{A-project-id}/{job_type}/{A-job-id}/...` (hosted mode) | Fail | Same advisory note as 2.6. |

## 6. Brand assets and config

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 6.1 | User B requests `GET /api/v1/brand/config` as B | Returns B's config (or 404 if none), never A's | Brand routes are user-scoped; guard is the authenticated identity. Hosted mode: `brand_config` RLS `user_id = auth.uid()`. |
| 6.2 | User B requests `GET /api/v1/brand/assets` as B | Response must not contain A's asset rows | Same as 6.1 on `brand_assets`. |
| 6.3 | User B requests `GET <signed-url-for-A-asset>` via a URL crafted by guessing A's asset path | Fail (signed URL was issued to A with short TTL; B cannot mint one) | Backend-issued signed URLs are scoped to the authenticated user via `get_brand_asset_url`. The `brand-assets` bucket is the only one whose runtime path (`{user_id}/brand/...`) satisfies the `auth.uid()` storage policy, so hosted-mode storage RLS is a real secondary barrier. |
| 6.4 | User B sends `DELETE /api/v1/brand/assets/{A-asset-id}` as B | 404 | Hosted mode: `brand_assets` RLS. Self-hosted: backend auth identity. |

## 7. Background task records

| # | Attempt | Expected | Guard of record |
|---|---|---|---|
| 7.1 | User B polls status of `background_tasks.id` belonging to a task targeting user A's source (`target_type='source'`) via `/api/v1/projects/{A-project-id}/sources/{A-source-id}/...` status routes as B | 404 | Project guard on the route. Hosted mode: polymorphic `background_tasks` RLS walks `target_id -> sources -> projects`. |
| 7.2 | User B polls status of a task targeting A's studio signal (`target_type='studio_signal'`) as B | 404 | Project guard + polymorphic RLS via `studio_signals -> chats -> projects` (hosted). |
| 7.3 | User B polls status of a task targeting A's chat (`target_type='chat'`) as B | 404 | Project guard + polymorphic RLS via `chats -> projects` (hosted). |
| 7.4 | User B attempts to cancel A's background task via any cancellation surface as B | 404 | Same as 7.1-7.3 per `target_type`. |

## Guardrails for test authors (NBB-107, NBB-702, NBB-703)

1. Each test must create at least two distinct users (A and B) and at least one project owned by A. Do not rely on a single-user fixture.
2. Tests must run against both deployment modes if the test harness supports it. At minimum, annotate the test with which mode it ran in.
3. Assert on the **guard path**: use a log probe, a spy on `has_project_access`, or an SQL-level RLS check. Do not assert only on HTTP status code — a silent bypass that returns 404 for an unrelated reason will still look green.
4. Do not assume hosted-mode RLS is defence-in-depth where this checklist says it is not. `studio_jobs`, `database_connections`, `mcp_connections`, and `freshdesk_tickets` have no RLS by design.
5. Keep storage-bucket direct-access tests behind a hosted-mode marker. In self-hosted mode, `Allow all on <bucket>` makes direct bucket access intentionally open to the backend identity.

## Cross-reference

- `backend/supabase/migrations/OWNERS.md`
- `backend/supabase/STORAGE_CONTRACTS.md`
- `backend/app/projects/CHARTER.md`, `backend/app/chat/CHARTER.md`, `backend/app/sources/CHARTER.md`, `backend/app/studio/CHARTER.md`, `backend/app/brand/CHARTER.md`, `backend/app/background/CHARTER.md`
- Ticket bodies: `docs/tickets/epics/NBB-001.md` (NBB-107), `docs/tickets/epics/NBB-007.md` (NBB-702, NBB-703)
