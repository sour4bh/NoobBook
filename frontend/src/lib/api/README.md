# `frontend/src/lib/api/` - Cross-stack API clients

This folder holds the thin TypeScript clients that call the Flask backend at
`/api/v1/...`. Each `*.ts` file wraps one backend route group (auth, chats, sources,
studio, etc.) and returns typed responses.

## Wire contracts

The wire contracts consumed by every file in this folder are cataloged in
[`docs/contracts/README.md`](../../../../docs/contracts/README.md) (NBB-205).

That document is the source of truth for:

- chat streaming event names (`user_message`, `ping`, `assistant_delta`, `assistant_done`, `error`)
- citation marker and chunk-id format (`[[cite:{source_id}_page_{n}_chunk_{m}]]`)
- chat tool invocation / result block union (`text | tool_use | tool_result | server_tool_use | web_search_tool_result | web_fetch_tool_result`)
- auth identity (`GET /auth/me`) and session (`POST /auth/signin|signup|refresh`) shapes
- authenticated media and scoped asset-token (`?asset_token=<token>`) access rules
- `studio_signals` row and tool-input shapes
- `projects.costs` and `chats.costs` JSONB shape
- `messages.content` JSONB block array shape
- background-task polling envelope (`/projects/<id>/active-tasks`)
- tool-schema JSON contract through domain-owned `tools/` directories and the backend asset registry
- source kind / MIME / status enums
- studio job status / progress / result flattening
- permissions JSON contract (`users.permissions` shape)

## Change discipline during migration

Any change that would alter a wire shape, rename a field, or add a new SSE event
name or studio enum value MUST update `docs/contracts/README.md` in the same
commit. Additive-only changes (new optional fields) are allowed inside migration
tickets NBB-301..304 (chat), NBB-401..403 (sources), NBB-501..507 (studio), and
NBB-602..604 (frontend) as long as the contract doc is updated.

Redesigning any listed contract is deferred in
[`docs/tickets/DEFERRED.md`](../../../../docs/tickets/DEFERRED.md) D-005.
