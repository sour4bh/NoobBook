# NoobBook Cross-Stack Contracts (NBB-205)

This document names the wire contracts that the backend publishes and the frontend
consumes, so parallel migration in Epics 003-006 cannot silently break them.

**Scope of this doc:** preserve current production behavior. Redesigning any contract
is deferred to `D-005` in `docs/tickets/DEFERRED.md` and is out of this ticket.

**Authority:** `NBB-204`'s charters (`backend/app/*/CHARTER.md`) name this file as the
shape owner for JSONB fields they catalog (`chats.costs`, `chats.selected_source_ids`,
`messages.content`, `background_tasks.progress`, studio rows, etc.). This file is the
source of truth for wire shape; the charters remain the access-control source of truth.

Each contract below carries seven fields:

1. Backend owner (file and symbol)
2. Frontend consumer (file)
3. Compatibility expectation during migration
4. Minimal valid example
5. Realistic current-production example
6. Invalid example (if runtime validation exists) or explicit "no runtime validation" note
7. Test plan

---

## Contract 1 - Chat streaming event format (SSE)

**Backend owner:**
- Transport: `backend/app/api/messages/routes.py::stream_message` (framing via `_format_sse`)
- Event producer: `app.chat.loop.ChatLoop._run_message_flow` and streaming bridge `app.chat.streaming.iter_chat_events` / `app.chat.streaming.call_claude`; emit machinery `app.chat.persistence.emit_event`

**Frontend consumer:** `frontend/src/lib/api/chats.ts` (SSE reader used by the chat view)

**Compatibility expectation:** The five event names and their payload shapes are frozen
for the migration. Framing (`event: <name>\ndata: <json>\n\n`) and response headers
(`Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`,
`Connection: keep-alive`, `X-Accel-Buffering: no`) are frozen. Adding a new event kind
requires a deferral entry in `DEFERRED.md` and a frontend change in the same merge.

**Event catalog (exact wire names, from `app.chat.schemas.CHAT_EVENT_NAMES`):**

| Event | Payload | Emitted by |
|---|---|---|
| `user_message` | stored user message row | after `message_service.add_user_message` |
| `ping` | `{}` | before each Claude call / loop iteration (keep-alive) |
| `assistant_delta` | `{"delta": "<partial text>"}` | per token chunk during streaming |
| `assistant_done` | stored assistant message row (same shape as non-streaming `assistant_message`) | after final text is persisted |
| `error` | `{"message": "<error string>", "assistant_message"?: <stored row>}` | on exception path; `assistant_message` present when a partial error row was persisted |

**Minimal valid example (wire framing):**

```text
event: ping
data: {}

```

**Realistic current-production example:**

```text
event: user_message
data: {"id":"m_01","role":"user","content":"What did Q3 say about revenue?","created_at":"2026-04-24T10:01:02Z"}

event: ping
data: {}

event: assistant_delta
data: {"delta":"Revenue grew "}

event: assistant_delta
data: {"delta":"15% "}

event: assistant_delta
data: {"delta":"[[cite:abc123_page_5_chunk_2]]."}

event: assistant_done
data: {"id":"m_02","role":"assistant","content":"Revenue grew 15% [[cite:abc123_page_5_chunk_2]].","model":"claude-sonnet-4-5-20250929","tokens":{"input_tokens":1240,"output_tokens":42}}
```

**Invalid example:** No runtime validation on event payload shape. The SSE framing is
produced by `_format_sse` which always emits the `event:`/`data:` pair; malformed JSON
inside `data:` would only be caught by the frontend parser. Treat the frontend SSE
reader as the validator.

**Test plan:**
- Extend `backend/tests/test_streaming_events.py` (new) to POST to
  `/api/v1/projects/<id>/chats/<id>/messages/stream`, tee the response stream, and
  assert every emitted chunk starts with `event: <name>\ndata: ` and ends with `\n\n`;
  assert the event sequence always begins with `user_message` and terminates with
  either `assistant_done` or `error`.
- Piggyback on `backend/tests/conftest.py` Claude mock fixture used by
  NBB-106 route smokes and NBB-109 cost tests; mock `app.chat.loop.ChatLoop._call_claude`
  to emit known deltas.

---

## Contract 2 - Citation marker and lookup format

**Backend owner:**
- Marker producer: Claude model output (system prompt in `backend/data/prompts/default_prompt.json`)
- Chunk ID format: `backend/app/sources/citations.py::parse_chunk_id` (regex `^(.+)_page_(\d+)_chunk_(\d+)$`)
- Lookup endpoint: `backend/app/api/sources/content.py::get_citation_content` at
  `GET /api/v1/projects/<project_id>/citations/<chunk_id>`

**Frontend consumer:** `frontend/src/lib/api/sources.ts` (citation fetch) and the chat
renderer that parses `[[cite:...]]` markers.

**Compatibility expectation:** Inline marker syntax (`[[cite:CHUNK_ID]]`) and chunk ID
shape (`{source_id}_page_{page}_chunk_{n}`) are frozen. The lookup response keys are
frozen: `success`, `chunk.{content, chunk_id, source_id, source_name, page_number, chunk_index}`.

**Minimal valid example (marker + lookup response):**

```text
Claude text: "See page 5 [[cite:abc_page_5_chunk_2]]."

GET /api/v1/projects/p1/citations/abc_page_5_chunk_2
-> 200
{
  "success": true,
  "chunk": {
    "content": "...",
    "chunk_id": "abc_page_5_chunk_2",
    "source_id": "abc",
    "source_name": "Q3.pdf",
    "page_number": 5,
    "chunk_index": 2
  }
}
```

**Realistic current-production example:**

```text
"Revenue grew 15% [[cite:a1b2c3d4-e5f6-7890-1234-56789abcdef0_page_5_chunk_2]]."

{
  "success": true,
  "chunk": {
    "content": "Q3 revenue reached $4.2B, up 15% year over year driven by...",
    "chunk_id": "a1b2c3d4-e5f6-7890-1234-56789abcdef0_page_5_chunk_2",
    "source_id": "a1b2c3d4-e5f6-7890-1234-56789abcdef0",
    "source_name": "Q3_Financial_Report.pdf",
    "page_number": 5,
    "chunk_index": 2
  }
}
```

**Invalid example (runtime validation exists):** `parse_chunk_id` returns `None` for
any chunk_id that does not match `^(.+)_page_(\d+)_chunk_(\d+)$`, and
`get_citation_content` then returns `404 {"success": false, "error": "Chunk not found: ..."}`.

```text
GET /api/v1/projects/p1/citations/abc_chunk_2
-> 404 {"success": false, "error": "Chunk not found: abc_chunk_2"}
```

**Test plan:**
- Extend `backend/tests/test_citations.py` (new) to unit-test `parse_chunk_id` across
  valid/invalid strings and integration-test `GET /citations/<chunk_id>` via the
  NBB-106 test app fixture for: (a) well-formed id that resolves, (b) well-formed id
  that misses, (c) malformed id.

---

## Contract 3 - Chat tool invocation/result wire format

**Backend owner:**
- Serialization: `backend/app/providers/anthropic/content.py::serialize_content_blocks` and
  `::build_tool_result_content`
- Schema loading: `backend/app/config/tool_loader.py`

**Frontend consumer:** The chat renderer indirectly via `messages.content` blocks
returned inside the saved message row. No direct tool-call UI today.

**Compatibility expectation:** Six discriminated `type` values are frozen:
`text`, `tool_use`, `tool_result`, `server_tool_use`, `web_search_tool_result`,
`web_fetch_tool_result`. The `tool_use_id` field pairs `tool_use` blocks to their
matching `tool_result` block.

**Block union (from `serialize_content_blocks`):**

```jsonc
// tool_use (client-side tool, e.g. search_sources)
{"type": "tool_use", "id": "toolu_01", "name": "search_sources",
 "input": {"source_id": "abc", "query": "revenue"}}

// tool_result paired by tool_use_id
{"type": "tool_result", "tool_use_id": "toolu_01",
 "content": "<JSON or text payload>", "is_error": false}

// server_tool_use (Claude-side, e.g. web_fetch/web_search)
{"type": "server_tool_use", "id": "srvu_01", "name": "web_fetch",
 "input": {"url": "https://example.com"}}

// server-side results
{"type": "web_search_tool_result", "tool_use_id": "srvu_01",
 "content": [{"url": "...", "title": "...", "cited_text": "..."}]}
{"type": "web_fetch_tool_result", "tool_use_id": "srvu_01",
 "content": {"type": "...", "url": "...", "content": {...}}}
```

**Minimal valid example:**

```json
[
  {"type": "tool_use", "id": "toolu_01", "name": "search_sources",
   "input": {"source_id": "abc"}},
  {"type": "tool_result", "tool_use_id": "toolu_01",
   "content": "[{\"chunk_id\":\"abc_page_1_chunk_0\",\"content\":\"...\"}]"}
]
```

**Realistic current-production example:** See Contract 9 (`messages.content`) for a
realistic multi-block conversation snippet.

**Invalid example:** `build_tool_result_content` coerces non-string `result` values via
`str(result)`, so a bad payload is not hard-rejected; however, the Anthropic API will
400 on an orphaned `tool_use` without a matching `tool_result`. The message_service
error path in `app.chat.loop.ChatLoop._run_message_flow` always writes a
`tool_result` even on tool failure. An invalid sequence — `tool_use` stored without a
following `tool_result` — breaks the next Claude call and is therefore the observed
failure mode.

**Test plan:**
- Extend `backend/tests/test_claude_parsing_utils.py` (existing; maps to `app.providers.anthropic.response_parser`) to unit-cover
  each of the six block types through `serialize_content_blocks` and
  `build_tool_result_content`.
- Integration case in the NBB-106 test app: send a mocked `tool_use` response, verify
  the stored message row contains `[tool_use, tool_result]` in order and matching ids.

---

## Contract 4 - Auth/session response contract

This heading covers two linked contracts: **identity** (`/auth/me`) and **session**
(`/auth/signin`, `/auth/signup`, `/auth/refresh`, `/auth/signout`).

**Backend owner:**
- Identity: `backend/app/api/auth/routes.py::me` + `backend/app/auth/identity.py::get_request_identity`
- Session: `backend/app/api/auth/routes.py::signup|signin|refresh|signout` +
  `backend/app/providers/supabase/auth.py::AuthService._serialize_user` and
  `::_serialize_session`

**Frontend consumer:** `frontend/src/lib/api/auth.ts`

**Compatibility expectation:** The two shapes below are frozen. Session fields come
from Supabase and must be stored client-side; the server does not hold session state.

**Identity response (`GET /auth/me`):**

```json
{
  "success": true,
  "auth_required": true,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "user",
    "is_admin": false,
    "is_authenticated": true
  }
}
```

**Session response (`POST /auth/signin|signup|refresh`):**

```json
{
  "success": true,
  "user": {"id": "uuid", "email": "user@example.com"},
  "session": {
    "access_token": "<JWT>",
    "refresh_token": "<opaque>",
    "expires_in": 3600,
    "token_type": "bearer"
  }
}
```

**Sign-out response (`POST /auth/signout`):** `{"success": true}`.

**Minimal valid example:** as above.

**Realistic current-production example:** as above with real Supabase-issued tokens;
`role` is one of `"admin" | "user"` (see `AuthService._resolve_signup_role`).

**Invalid example (runtime validation exists):**
- `/auth/signin` with missing/empty email or password -> `400 {"success": false, "error": "email and password are required"}`.
- `/auth/refresh` with missing `refresh_token` -> `400 {"success": false, "error": "refresh_token is required"}`.
- `/auth/refresh` with an invalid refresh token -> `401` with Supabase error payload.

**Test plan:**
- `backend/tests/test_auth_identity.py` and `backend/tests/test_auth_session.py` (owned
  by `NBB-107` tests; NBB-205 just catalogs the shapes). Assertions:
  `/auth/me` returns the identity shape above in both `auth_required=true` and
  `auth_required=false` modes; `/auth/signin` success returns the four session keys;
  `/auth/signin` with empty body returns 400 with the fixed error string.

---

## Contract 5 - Authenticated media / generated-asset access

**Backend owner:** Any `backend/app/api/**/*.py` route that calls
`storage_service.download_*` and returns a binary `Response(...)`. Representative
examples:
- `backend/app/api/sources/content.py::get_ai_image` (AI-generated images)
- `backend/app/api/studio/audio.py` (audio overview MP3s)
- `backend/app/api/studio/videos.py` (video MP4s)
- `backend/app/api/studio/emails.py::preview_email_template` (HTML)
- `backend/app/api/studio/websites.py` (HTML + assets)

**Frontend consumer:** `frontend/src/lib/api/sources.ts` and `frontend/src/lib/api/studio/*`
plus direct `<img>/<video>/<iframe>` tags in the rendered DOM.

**Compatibility expectation:** Authenticated asset access uses the `Authorization:
Bearer <jwt>` header by default. Responses are binary with the asset's native
`Content-Type`. No route-level standardized envelope for binary GETs. 404 JSON errors
use `{"success": false, "error": "<message>"}`.

**Minimal valid example:**

```text
GET /api/v1/projects/<id>/ai-images/abc123_chart.png
Authorization: Bearer <jwt>
-> 200 Content-Type: image/png
<binary>
```

**Realistic current-production example (from `get_ai_image`):** MIME resolved via
extension map (`png|jpg|jpeg|gif|webp|svg` -> `image/*`), default `image/png`.

**Invalid example (runtime validation exists):**
- Missing or invalid JWT -> `401` from the project-access guard in
  `backend/app/__init__.py` before the route runs.
- Asset not found -> `404 {"success": false, "error": "Image not found: ..."}`.

**Test plan:**
- Extend `backend/tests/test_media_access.py` (new) to cover one image route
  (`/ai-images/<file>`) and one studio route (`/studio/audio/<job_id>/<file>`) with:
  valid JWT + present file (200 + correct `Content-Type`), valid JWT + missing file
  (404 JSON), missing/invalid JWT (401). Reuse NBB-106 test app fixtures.

---

## Contract 6 - Query-token asset access

**Backend owner:** `backend/app/auth/access.py::get_current_user_id`
(current request identity) and `backend/app/api/auth/middleware.py`
(Bearer-token and query-token extraction).
Call sites that inject the token into rendered HTML:
- `backend/app/api/studio/emails.py::preview_email_template` (rewrites `src="..."` to append `?token=<jwt>`)
- `backend/app/api/studio/websites.py` (same pattern for CSS/JS/image URLs)
- `backend/app/api/transcription/routes.py` (ElevenLabs WebSocket URL carries `?token=` but that token is an ElevenLabs single-use token, not the Supabase JWT).

**Frontend consumer:** `frontend/src/lib/api/studio/emails.ts`,
`frontend/src/lib/api/studio/websites.ts`, and the iframe components that render HTML
previews.

**Compatibility expectation:** The query token IS the Supabase JWT — same secret, same
lifecycle as the `Authorization: Bearer` header. The only difference is transport
location. This exists because `<img>`, `<video>`, `<audio>`, and `<iframe>` elements
cannot attach custom headers. Transcription is the single exception: the
`?token=` on the ElevenLabs WebSocket URL is an ElevenLabs-issued token.

**Minimal valid example:**

```text
GET /api/v1/projects/<id>/ai-images/chart.png?token=<JWT>
-> 200 image/png
```

**Realistic current-production example (email template preview iframe):**

```text
GET /api/v1/projects/p1/studio/email-templates/j1/preview?token=<JWT>
-> 200 text/html

HTML body contains rewritten inline image refs:
<img src="/api/v1/projects/p1/studio/email-templates/j1/hero.png?token=<JWT>">
```

**Invalid example (runtime validation exists):**
- No `Authorization` header and no `?token=` -> `auth_middleware` logs a warning and
  returns `None`, causing the project guard to return 401/404 JSON.
- `?token=` present but not a valid Supabase JWT -> `supabase.auth.get_user(token)`
  raises, middleware logs "Token validation failed", returns 401/404.

**Test plan:**
- Extend `backend/tests/test_media_access.py` (see Contract 5) with a query-param
  path: `GET /ai-images/<file>?token=<valid_jwt>` returns 200; same URL without token
  returns 401/404; invalid token returns 401/404.

---

## Contract 7 - `studio_signals` / studio event shape

There are two layered contracts here: the **tool input** Claude produces, and the
**row shape** persisted in Supabase.

**Backend owner:**
- Tool input + row writer: `backend/app/studio/signal/__init__.py::StudioSignalExecutor.emit` and `::_store_signals`
- Table: `studio_signals` in `backend/supabase/migrations/` (owned by the chat charter as a cross-table write)

**Frontend consumer:** `frontend/src/lib/api/chats.ts` (the chat detail response
includes a `studio_signals` array per `backend/app/chat/store.py::get_chat`)

**Compatibility expectation:** The 18-item `studio_item` enum (listed below) is frozen
until `NBB-501A` runs. Layered optional fields for `blog` and `business_report` are
frozen. The row's `status` enum is `"pending"` on insert; downstream studio job
creation flips it.

**Tool input (what Claude emits through the `studio_signal` tool):**

```json
{
  "signals": [
    {
      "studio_item": "<enum>",
      "direction": "<optional string>",
      "sources": [{"source_id": "<uuid>", "chunk_ids": ["..."]}],
      "target_keyword": "<blog only>",
      "blog_type": "<blog only>",
      "report_type": "<business_report only>",
      "csv_source_ids": ["..."],
      "context_source_ids": ["..."],
      "focus_areas": ["..."]
    }
  ]
}
```

`studio_item` enum (frozen list, from `valid_items` in the executor):
`quiz | flash_cards | audio_overview | mind_map | business_report | marketing_strategy | prd | infographics | flow_diagram | blog | social | website | email_templates | components | ads_creative | video | presentation | wireframes`.

**Row shape (what lands in `studio_signals`):**

```json
{
  "id": "uuid",
  "chat_id": "uuid",
  "studio_item": "<enum>",
  "direction": "string",
  "source_ids": ["uuid", "..."],
  "status": "pending",
  "created_at": "<ISO8601>"
}
```

**Minimal valid example (tool input):**

```json
{"signals": [{"studio_item": "quiz", "direction": "10 MCQs", "sources": []}]}
```

**Realistic current-production example:**

```json
{"signals": [
  {"studio_item": "audio_overview", "direction": "Conversational tone, ~6 min",
   "sources": [{"source_id": "a1b2", "chunk_ids": ["a1b2_page_1_chunk_0"]}]},
  {"studio_item": "business_report", "direction": "Summarize Q3 vs Q2",
   "report_type": "executive_summary",
   "csv_source_ids": ["c3d4"], "context_source_ids": ["a1b2"],
   "focus_areas": ["revenue", "churn"], "sources": []}
]}
```

**Invalid example (runtime validation exists):** Any signal with a `studio_item` outside
the enum is dropped by `StudioSignalExecutor.emit` with a warning log; the row is
never written. An all-invalid input returns
`{"success": false, "message": "No valid signals to store"}` to Claude.

**Test plan:**
- `backend/tests/test_studio_signal_executor.py` (new): call `.emit(...)` with (a)
  valid enum + empty sources (asserts fallback source fill from
  `_get_fallback_source_ids`), (b) unknown `studio_item` (dropped, 0 rows inserted),
  (c) blog signal preserves `target_keyword` and `blog_type`, (d) business_report
  preserves the four optional fields.

---

## Contract 8 - `projects.costs` JSONB shape

**Backend owner:**
- Writer: `backend/app/providers/anthropic/cost.py::_apply_usage` and `::update_project_costs`
- Default/ensure: `::_get_default_costs`, `::_ensure_cost_structure`
- Read endpoint: `backend/app/api/projects/costs.py::get_project_costs_endpoint`

**Frontend consumer:** `frontend/src/lib/api/projects.ts` (ProjectHeader tooltip)

**Compatibility expectation:** Top-level keys `total_cost` and `by_model` are frozen.
Every model bucket key in `_MODEL_KEYS = ("opus", "sonnet", "haiku")` is always
initialized, even if never used. Per-bucket keys `input_tokens`, `output_tokens`,
`cost` are frozen. `chats.costs` mirrors this shape (see `backend/app/chat/CHARTER.md`).

**Minimal valid example:**

```json
{
  "total_cost": 0.0,
  "by_model": {
    "opus":   {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
    "sonnet": {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
    "haiku":  {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}
  }
}
```

**Realistic current-production example:**

```json
{
  "total_cost": 0.0234,
  "by_model": {
    "opus":   {"input_tokens": 0,    "output_tokens": 0,    "cost": 0.0},
    "sonnet": {"input_tokens": 5000, "output_tokens": 1500, "cost": 0.0225},
    "haiku":  {"input_tokens": 2000, "output_tokens": 500,  "cost": 0.0009}
  }
}
```

**Invalid example (runtime validation exists):** `_ensure_cost_structure` repairs any
JSONB read whose `total_cost` or `by_model` keys are missing (zero-fills). Unknown
model strings collapse to `"sonnet"` via `_get_model_key`. Therefore the only way to
produce an invalid persisted shape is to write outside `_apply_usage`; the
`NBB-109`-landed `verify_project_id_coverage.py` guards against skipping `project_id`.

**Test plan:**
- Reuse `backend/tests/test_claude_cost_tracking.py` and `test_cost_tracking.py` from
  `NBB-109`. Add a contract assertion: given a project with empty costs, after a call
  with `model="claude-sonnet-4-5-20250929"` the persisted row has exactly the three
  `by_model` keys above and `total_cost == sonnet.cost`.

---

## Contract 9 - `messages.content` JSONB shape

**Backend owner:**
- Writer: `backend/app/chat/message/store.py` (via
  `app.providers.anthropic.content.serialize_content_blocks` and `build_tool_result_content`)
- Reader: `backend/app/chat/message/store.py::build_api_messages`

**Frontend consumer:** `frontend/src/lib/api/chats.ts`; the chat renderer parses
`text` blocks for `[[cite:...]]` markers and ignores `tool_use`/`tool_result` blocks.

**Compatibility expectation:** `messages.content` is an array of Claude content blocks.
The accepted `type` discriminators are identical to Contract 3 (`text`, `tool_use`,
`tool_result`, `server_tool_use`, `web_search_tool_result`, `web_fetch_tool_result`).
Role is `"user" | "assistant"`. `tool_result` blocks are stored on `user`-role rows;
`tool_use` blocks are stored on `assistant`-role rows. This pairing is what
`build_api_messages` replays to Claude.

**Minimal valid example:**

```json
[{"type": "text", "text": "Hello"}]
```

**Realistic current-production example (full turn with tool use):**

```json
// assistant row #1: text + tool_use in same turn
[
  {"type": "text", "text": "Let me search the sources."},
  {"type": "tool_use", "id": "toolu_01", "name": "search_sources",
   "input": {"source_id": "a1b2", "query": "revenue Q3"}}
]

// user row #2: tool_result paired by tool_use_id
[
  {"type": "tool_result", "tool_use_id": "toolu_01",
   "content": "[{\"chunk_id\":\"a1b2_page_5_chunk_2\",\"content\":\"...\"}]"}
]

// assistant row #3: final text with citation marker
[
  {"type": "text",
   "text": "Q3 revenue grew 15% [[cite:a1b2_page_5_chunk_2]]."}
]
```

**Invalid example:** No runtime validator on the JSONB field; validation is implicit
via `build_api_messages` replay -- an orphaned `tool_use` with no matching `tool_result`
causes Anthropic to return 400 on the next call. The `app.chat.loop.ChatLoop` loop writes
`tool_result` even on tool exceptions to prevent orphaned `tool_use`.

**Test plan:**
- Shared with Contract 3. Add one round-trip assertion: write a message row with each
  block-type via `message_service.add_message`, then call `build_api_messages` and
  assert the replay matches the Anthropic message-sequence rules
  (user/assistant alternation, paired ids). File: `backend/tests/test_messages_content_contract.py` (new).

---

## Contract 10 - Background-task polling response

**Backend owner:** `backend/app/api/projects/active_tasks.py::get_active_tasks` at
`GET /api/v1/projects/<project_id>/active-tasks`.

Reads from three sources: `sources` (processing + embedding statuses), `studio_jobs`
(pending + processing), and `background_tasks` (pending + running); merges them into
one normalized task list.

**Frontend consumer:** The status bar component that polls this endpoint from
`frontend/src/lib/api/projects.ts`.

**Compatibility expectation:** Response envelope (`success`, `tasks[]`, `count`) is
frozen. Task `type` enum is frozen: `"source" | "studio" | "background"`. Task status
strings are inherited from each underlying table and are frozen per Contracts 12 and
13 below.

**Minimal valid example:**

```json
{"success": true, "tasks": [], "count": 0}
```

**Realistic current-production example:**

```json
{
  "success": true,
  "tasks": [
    {"id": "s1", "type": "source", "label": "Q3 Report.pdf",
     "detail": "Processing...", "status": "processing",
     "created_at": "2026-04-24T10:00:00Z"},
    {"id": "j1", "type": "studio", "label": "Audio Overview",
     "detail": "Q3 Report.pdf", "status": "processing",
     "progress": "Generating script...",
     "created_at": "2026-04-24T10:00:05Z"},
    {"id": "b1", "type": "background", "label": "Naming Chat",
     "detail": "Processing...", "status": "running",
     "created_at": "2026-04-24T10:00:10Z"}
  ],
  "count": 3
}
```

**Invalid example:** No runtime validation. Partial-fetch failures are swallowed (the
route logs a warning and returns the tasks that did resolve, still inside the frozen
envelope). Therefore any response with `success: true` is guaranteed to carry the
three required envelope keys.

**Test plan:**
- `backend/tests/test_active_tasks.py` (new): seed one `sources` row in
  `processing`, one `studio_jobs` row in `pending`, one `background_tasks` row in
  `running`; assert the three keys `success`/`tasks`/`count` and that each task
  object carries `id`, `type`, `label`, `detail`, `status`, `created_at`.

---

## Contract 11 - Tool-schema JSON contract

**Backend owner:**
- Loader: `backend/app/config/tool_loader.py` (NBB-207A)
- Registered asset paths: domain-owned `tools/` directories mapped by
  `backend/app/config/asset_registry.py`

**Frontend consumer:** None directly. Tool schemas are consumed by Claude; the
frontend sees their effects through `tool_use` / `tool_result` blocks (Contract 3).

**Compatibility expectation:** Each file is a single JSON object conforming to
Anthropic's tool schema: `{"name": str, "description": str, "input_schema":
{"type": "object", "properties": {...}, "required": [...]}}`. Schema versioning is by
filename and directory; the loader registry in NBB-207A governs path portability
during migration.

**Minimal valid example (from `chat_tools/source_search_tool.json`):**

```json
{
  "name": "search_sources",
  "description": "Search for information in ...",
  "input_schema": {
    "type": "object",
    "properties": {
      "source_id": {"type": "string", "description": "..."},
      "keywords": {"type": "array", "items": {"type": "string"}},
      "query":    {"type": "string"}
    },
    "required": ["source_id"]
  }
}
```

**Realistic current-production example:** tool JSON files live beside their
owning domains, such as `backend/app/chat/tools/source_search_tool.json`,
`backend/app/chat/memory/tools/memory_tool.json`,
`backend/app/connectors/jira/tools/jira_search_issues.json`, and
`backend/app/studio/signal/tools/studio_signal_tool.json`. Legacy loader
category keys are preserved by registry mappings, not by directory layout.

**Invalid example (runtime validation exists):** The Anthropic API rejects any request
whose `tools[]` array fails JSON-schema validation against its `input_schema`. A
missing `name` or malformed `input_schema` surfaces as a 400 from Claude on the first
call that includes the tool; our loader does not currently pre-validate shape.

**Test plan:**
- Extend `backend/tests/test_tool_loader.py` (owned by NBB-207A) with a per-file
  structural check: every registered tool `*.json` must parse as JSON and carry
  `name`, `description`, and `input_schema.type == "object"`. Place
  the NBB-205-owned assertion in `backend/tests/test_tool_schema_contract.py` (new) so
  ownership is clear.

---

## Contract 12 - Source kind / MIME / status

**Backend owner:**
- Kind + MIME: `backend/app/sources/file_contract.py::ALLOWED_EXTENSIONS` and `::MIME_TYPES`, plus `::get_file_info`
- Status: `backend/app/sources/catalog.py::SourceCatalog.update_source` (status writes) and the per-type processors under `backend/app/sources/**/process.py`
- Row: `sources` table; charter owner `backend/app/sources/CHARTER.md`

**Frontend consumer:** `frontend/src/lib/api/sources.ts`

**Compatibility expectation:** Three frozen enums:

- **Category** (from `ALLOWED_EXTENSIONS` values): `document | audio | image | data | link`.
- **Source `type` string** (response field, per `file_upload.py` line 102/193):
  uppercased category -> `DOCUMENT | AUDIO | IMAGE | DATA | LINK`. URL/YouTube
  sources use `LINK` today. Migration tickets NBB-401/402/403 MUST preserve these
  display types.
- **Status enum** (from `source_service.update_source` call sites):
  `uploaded -> processing -> [embedding] -> ready | error | cancelled`.

Extension -> category mapping (frozen during migration):

```
document: .pdf .txt .docx .pptx .md .json .html .xml
audio:    .mp3 .wav .m4a .aac .flac
image:    .jpeg .jpg .png .gif .webp
data:     .csv
link:     .link
```

Integration kinds use synthetic extensions (`.database`, `.freshdesk`, `.jira`,
`.mixpanel`) stored in `embedding_info.file_extension` but carry `type: DATA`.

**Minimal valid example (source row):**

```json
{
  "id": "uuid",
  "name": "Q3.pdf",
  "type": "DOCUMENT",
  "status": "ready",
  "embedding_info": {"file_extension": ".pdf", "stored_filename": "..."}
}
```

**Realistic current-production example:**

```json
{
  "id": "a1b2c3d4",
  "project_id": "p1",
  "name": "Q3_Financial_Report.pdf",
  "type": "DOCUMENT",
  "status": "ready",
  "token_count": 18420,
  "embedding_info": {
    "file_extension": ".pdf",
    "stored_filename": "a1b2c3d4.pdf",
    "is_embedded": true
  }
}
```

**Invalid example (runtime validation exists):** `is_allowed_file` rejects unknown
extensions; upload routes return 400 on unsupported types. A status value outside the
frozen enum cannot be written through `update_source` without passing the string
unchanged -- there is no enum validator. The contract guard is "only the processors
and upload routes write `status`, and they use string literals from the enum above".

**Test plan:**
- `backend/tests/test_sources_contract.py` (new): assert `get_file_info(name)` for
  one file per category returns the documented `(ext, category, mime)` triple;
  assert `list_sources` results carry `type` in uppercase category form; simulate
  each status transition through `source_service.update_source` on a seeded row and
  assert the final `sources` row value.

---

## Contract 13 - Studio job status / progress / result

**Backend owner:**
- Writer: `backend/app/studio/jobs/store.py::create_job` and `::update_job`
- Table: `studio_jobs` in `backend/supabase/migrations/00009_studio_jobs.sql` and
  follow-ups (see `backend/app/studio/CHARTER.md`)
- Per-type readers: `backend/app/api/studio/<type>.py` (e.g., `audio.py`, `videos.py`)

**Frontend consumer:** `frontend/src/lib/api/studio/*`

**Compatibility expectation:** Status enum
`pending | processing | ready | error | cancelled`. `progress` is a human-readable
string (not a percentage). Top-level columns are
`status, progress, error_message, started_at, completed_at, source_name, direction,
source_id`; everything else lives inside the `job_data` JSONB and is flattened on
read by `_map_job`.

**Minimal valid example (created row):**

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "job_type": "audio",
  "status": "pending",
  "progress": null,
  "source_id": "uuid",
  "source_name": "Q3.pdf",
  "direction": null,
  "job_data": {}
}
```

**Realistic current-production example (audio overview mid-flight):**

```json
{
  "id": "j1",
  "project_id": "p1",
  "job_type": "audio",
  "status": "processing",
  "progress": "Generating script (step 2)...",
  "source_id": "a1b2",
  "source_name": "Q3_Financial_Report.pdf",
  "direction": "Create an engaging audio overview of this content.",
  "started_at": "2026-04-24T10:00:05Z",
  "completed_at": null,
  "error_message": null,
  "audio_url": "/api/v1/projects/p1/studio/audio/j1/output.mp3",
  "script_preview": "..."
}
```

Note: `error` is a read-time alias of `error_message` (see
`studio_index_service._map_job`).

**Invalid example (runtime validation exists):** Any update through `update_job`
passes through a column-vs-JSONB split in the service; there is no enum validator on
`status`. Downstream consumers (the per-type `*.py` routes) rely on the enum above
and return 404/422 for unexpected values. For example, `audio_overview` edit flow
returns 404 when `parent_job_id` points at a missing job (see `emails.py` preview
pattern).

**Test plan:**
- `backend/tests/test_studio_jobs_contract.py` (new): create a job via
  `studio_index_service.create_job`, transition through each status via
  `update_job`, assert the flattened dict shape returned matches the example above
  (JSONB `audio_url`/`script_preview` merged to top level, `error_message` aliased).

---

## Contract 14 - Permissions JSON contract

**Backend owner:** `backend/app/auth/permissions.py::_get_default_permissions`,
`::get_user_permissions`, `::update_user_permissions`; enforcement decorator
`backend/app/auth/guards.py::require_permission`. Stored in
`users.permissions` JSONB; `NULL` means "use defaults".

**Frontend consumer:** `frontend/src/lib/api/settings.ts` (admin permissions modal)

**Compatibility expectation:** Five frozen top-level categories:
`document_sources, data_sources, studio, integrations, chat_features`. Each category
has `{"enabled": bool, "items": {<item_key>: bool}}`. Item keys are frozen -- adding
or removing any item requires coordinated frontend + permissions-modal change. The
merge-with-defaults behavior in `get_user_permissions` ensures stored rows upgrade
gracefully when new item keys are introduced by defaults.

**Minimal valid example (the all-enabled default):**

```json
{
  "document_sources": {"enabled": true, "items": {
    "pdf": true, "docx": true, "pptx": true, "image": true,
    "audio": true, "url_youtube": true, "text": true, "google_drive": true}},
  "data_sources": {"enabled": true, "items": {
    "database": true, "csv": true, "freshdesk": true, "jira": true, "mixpanel": true}},
  "studio": {"enabled": true, "items": {
    "audio_overview": true, "ad_creative": true, "flash_cards": true,
    "flow_diagrams": true, "infographics": true, "mind_maps": true,
    "quizzes": true, "social_posts": true, "emails": true, "websites": true,
    "components": true, "videos": true, "wireframes": true,
    "presentations": true, "prds": true, "marketing_strategies": true,
    "blogs": true, "business_reports": true}},
  "integrations": {"enabled": true, "items": {
    "jira": true, "mixpanel": true, "notion": true, "mcp": true, "elevenlabs": true}},
  "chat_features": {"enabled": true, "items": {
    "memory": true, "voice_input": true, "chat_export": true}}
}
```

**Realistic current-production example (a user with blogs+websites disabled):**

```json
{
  "studio": {"enabled": true, "items": {
    "blogs": false, "websites": false, "audio_overview": true,
    "ad_creative": true, "flash_cards": true, "flow_diagrams": true,
    "infographics": true, "mind_maps": true, "quizzes": true,
    "social_posts": true, "emails": true, "components": true,
    "videos": true, "wireframes": true, "presentations": true,
    "prds": true, "marketing_strategies": true, "business_reports": true}},
  "...": "other categories unchanged from defaults"
}
```

**Invalid example (runtime validation exists):** `require_permission("studio",
"blogs")` on a route returns 403 if the user's resolved permissions have
`studio.enabled == false` or `studio.items.blogs == false`. The decorator is the
runtime validator; the storage layer itself does not schema-check.

**Test plan:**
- Add `backend/tests/test_permissions_contract.py` (new, sibling to NBB-107 auth
  tests). Assertions: the default shape returned by `get_user_permissions(user_id)`
  for a user with `permissions=NULL` has the five category keys and every item key
  enumerated above; a user with `{"studio": {"enabled": true, "items": {"blogs":
  false}}}` merged with defaults yields all studio items `true` except `blogs`;
  hitting `/studio/blogs` with that user returns 403.

---

## Contract 15 - `chats.selected_source_ids` tri-state

This contract is pulled in explicitly because `backend/app/chat/CHARTER.md` (NBB-204)
names NBB-205 as its shape owner.

**Backend owner:**
- Column: `backend/supabase/migrations/00013_chat_selected_sources.sql`
- Write path: `backend/app/chat/store.py::update_chat`
  (allowed_fields includes `selected_source_ids`)
- Read path: `app.chat.loop.ChatLoop._run_message_flow` + `context_loader.get_active_sources`

**Frontend consumer:** `frontend/src/lib/api/chats.ts` plus the chat-view source
picker. Updates via `PUT /api/v1/projects/<id>/chats/<chat_id>`.

**Compatibility expectation:** Three-valued contract. Any chat-store migration
(NBB-209A, NBB-301) must preserve the null-vs-empty distinction; collapsing `NULL`
into `[]` silently breaks legacy chats.

| Value | Meaning |
|---|---|
| `NULL` | Legacy chat or never-set; fall back to all `ready + active` project sources. |
| `[]` | Explicit "no sources selected"; chat runs with zero source context. |
| `["uuid", ...]` | Explicit subset of project source ids. |

**Minimal valid example:** `null`, `[]`, or `["a1b2c3d4"]`.

**Realistic current-production example:**

```json
{"selected_source_ids": ["a1b2c3d4-e5f6-7890-1234-56789abcdef0",
                         "b2c3d4e5-f6a7-8901-2345-6789abcdef01"]}
```

**Invalid example:** No runtime enum validator; any non-null/non-array write would
break `context_loader.get_active_sources`. `chat_service.update_chat` only whitelists
the column, it does not type-check its value. Downstream the read path treats
non-list + non-null as a bug and will raise. In practice the upstream writers
(chat-edit endpoint and source picker UI) are the shape guards.

**Test plan:**
- `backend/tests/test_selected_source_ids_contract.py` (new). Three cases:
  (a) `NULL` stored -> `app.chat.loop.ChatLoop._run_message_flow` reads all `ready + active` sources;
  (b) `[]` stored -> zero sources in context;
  (c) `["<id>"]` stored -> exactly that subset reaches `context_loader`.
  Reuse the NBB-106 route-smoke test app + a mock for
  `app.chat.loop.ChatLoop._call_claude`.

---

## Cross-reference

- Access-control (who can call these endpoints) is owned by `NBB-107` tests and the
  NBB-204 charters; this doc only covers shapes.
- Redesign of any contract above is deferred in `docs/tickets/DEFERRED.md` D-005.
- `backend/app/chat/CHARTER.md` (NBB-204) explicitly defers wire-shape ownership for
  `chats.costs`, `chats.selected_source_ids`, and `messages.content` to this doc.
- Loader registry for tool schemas (Contract 11) is owned by `NBB-207A`; prompt/tool
  JSON movement is `NBB-207B` and `NBB-207C`.
