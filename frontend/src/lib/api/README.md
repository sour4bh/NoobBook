# `frontend/src/lib/api/` - Cross-stack API clients

This folder holds the thin TypeScript clients that call the Flask backend at
`/api/v1/...`. Each `*.ts` file wraps one backend route group (auth, chats, sources,
studio, etc.) and returns typed responses.

Runtime parsing for preserved public contracts lives in `contracts.ts`. API
clients should parse covered backend DTOs once at this boundary, then pass typed
values inward. Chat SSE uses the same token-refresh retry path as axios calls via
`fetchWithAuthRefresh`.

## Wire contracts

The wire contracts consumed by every file in this folder are cataloged in
[`docs/contracts/README.md`](../../../../docs/contracts/README.md) (NBB-205).

That document is the source of truth for:

- chat streaming event names (`user_message`, `ping`, `assistant_delta`, `assistant_done`, `error`)
- citation marker and chunk-id format (`[[cite:{source_id}_page_{n}_chunk_{m}]]`)
- chat content-part union (`text | media | tool_call | tool_result | provider_metadata`)
- auth identity (`GET /auth/me`) and session (`POST /auth/signin|signup|refresh`) shapes
- authenticated media and scoped asset-token (`?asset_token=<token>`) access rules
- `studio_signals` row and tool-input shapes
- `projects.costs` and `chats.costs` JSONB shape
- `messages.content` JSONB block array shape
- background-task polling envelope (`/projects/<id>/active-tasks`)
- tool-spec contract through domain-owned `tools/specs.py` modules and the backend asset registry
- source kind / MIME / status enums
- studio job status / progress / result flattening
- permissions JSON contract (`users.permissions` shape)

## Change discipline during migration

Any change that would alter a wire shape, rename a field, or add a new SSE event
name or studio enum value MUST update `docs/contracts/README.md` in the same
commit. Additive-only changes (new optional fields) are allowed inside migration
tickets NBB-301..304 (chat), NBB-401..403 (sources), NBB-501..507 (studio), and
NBB-602..604 (frontend) as long as the contract doc is updated.

Redesign beyond the preserved contracts and runtime parser coverage is narrowed
in [`docs/tickets/DEFERRED.md`](../../../../docs/tickets/DEFERRED.md) D-005.
