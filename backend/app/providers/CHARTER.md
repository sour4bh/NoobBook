# `providers/` boundary charter (NBB-206)

**Owner:** NBB-206 overlays this charter on top of the package-level import/dependency charter in `backend/app/providers/__init__.py` (authored by NBB-104). Read the `__init__.py` charter first; this file finalizes the external-edge rules the `__init__.py` defers to NBB-206.

**Scope:** `providers/` owns the outermost edge of the backend. Everything here speaks an external protocol or a runtime IO primitive and exposes a thin, typed surface for the rest of the backend.

Provider territory:
- Low-level external API clients and SDK wrappers (Anthropic, OpenAI, ElevenLabs, Gemini, Veo, Imagen, Pinecone, Tavily, Webshare).
- Raw storage and database adapters (Supabase storage, Supabase auth client, Supabase service-role client).
- Auth primitives tied to a specific provider protocol (Google OAuth token exchange and refresh).
- Raw transport wrappers for connector runtimes (MCP SSE/stdio client).
- Provider-neutral runtime IO consumed directly by domains (HTTP fetches, YouTube transcript fetch, media/base64 encoding helpers, rate limiters paired with a specific provider API, Claude response parsers and cost helpers).

## Out of scope

- Product orchestration. If a capability is named after a product integration (Notion workspace, Jira project, Freshdesk ticket scope, Mixpanel project, Google Drive folder), it is a connector, not a provider.
- User/project connection state. Connector stores (database connection, MCP connection) belong to `connectors/`, not `providers/` — see `NBB-209E`.
- Permission-gated tool schemas. Claude-visible tool JSON that depends on per-user credentials lives under `connectors/<name>/tools/` by the `NBB-207C` decision map.
- File-format parsing and extraction. PDF, DOCX, PPTX, image, audio, URL, and YouTube *format* operations are domain-owned behavior under `sources/` (see `NBB-401`). `providers/` supplies raw fetch/transport primitives; it does not extract structured content from bytes.
- Studio export and screenshot helpers. Studio-owned behavior under `studio/` owns those.

`platform/files/` and `providers/files/` are explicitly rejected as default homes. There is no generic file-adapter root; format ownership follows `NBB-401`, and provider-neutral IO primitives stay near the protocol they speak.

## Dependency direction (providers view)

`providers/` is a leaf in the import graph.

- `providers/` imports nothing from `api/`, any domain (`chat/`, `sources/`, `studio/`, `projects/`, `auth/`, `brand/`, `settings/`, `background/`), or `connectors/`.
- `connectors/` imports from `providers/` to wrap a raw client into a configured product capability.
- Domains may import from `providers/` **only** for provider-neutral runtime primitives (HTTP/storage/Anthropic-client/OpenAI-embeddings primitives). Product-specific external capabilities go through `connectors/` instead.
- Domain-reviewed provider seam: `sources/CHARTER.md` pins `providers/supabase/storage_service.py` (currently `services/integrations/supabase/storage_service.py`) as the single path builder for the `raw-files`, `processed-files`, and `chunks` buckets. Do not introduce sibling path builders; the seam crosses the boundary by design and is reviewed under `NBB-204`.

Rich import-direction enforcement lands in `NBB-704A` and `NBB-704B`.

## Current-code inventory

Classification of today's `backend/app/services/integrations/` subtree against the providers/connectors split. No code moves in this ticket. Target shape is `backend/app/providers/<name>/`; the actual move plan lives in `NBB-705C` (Anthropic-family utilities) and the per-domain/per-connector tickets that follow.

| Current path | Classification | Rationale |
|---|---|---|
| `services/integrations/claude/claude_service.py` | provider | Raw Anthropic Messages API client; `NBB-705C` drains Claude parsing/cost/rate helpers alongside it into `providers/anthropic/`. |
| `services/integrations/openai/openai_service.py` | provider | Raw OpenAI embeddings client; stateless, no product orchestration. |
| `services/integrations/elevenlabs/audio_service.py` | provider | ElevenLabs Scribe v1 transcription SDK call. |
| `services/integrations/elevenlabs/transcription_service.py` | provider | ElevenLabs streaming-transcription token minting (runtime IO primitive). |
| `services/integrations/elevenlabs/tts_service.py` | provider | ElevenLabs TTS SDK call. |
| `services/integrations/pinecone/pinecone_service.py` | provider | Vector DB client + index lifecycle; auto-index creation is a provider concern. |
| `services/integrations/tavily/tavily_service.py` | provider | Raw Tavily search SDK call. |
| `services/integrations/supabase/supabase_client.py` | provider | Shared Supabase service-role client factory. |
| `services/integrations/supabase/auth_service.py` | provider | Supabase auth SDK wrapper (identity primitives). |
| `services/integrations/supabase/storage_service.py` | provider (domain-reviewed seam) | Bucket path builder and upload/download primitive; `sources/CHARTER.md` names it as the single writer for source buckets. |
| `services/integrations/google/google_auth_service.py` | provider | Google OAuth 2.0 token exchange and refresh — a protocol primitive separate from any Google product capability. |
| `services/integrations/google/imagen_service.py` | provider | Raw Gemini Pro Image model client. Matches the `GEMINI_*`/`NANO_BANANA_API_KEY` → `providers/` rows in `NBB-208A`. |
| `services/integrations/google/video_service.py` | provider | Raw Veo API client. Matches the `VEO_API_KEY` → `providers/` row in `NBB-208A`. |
| `services/integrations/youtube/youtube_service.py` | provider | Provider-neutral fetch primitive (`youtube-transcript-api`) consumed directly by `sources/`; no product/connector state. |
| `services/integrations/mcp/mcp_client.py` | provider | SSE/stdio transport wrapper around the MCP SDK; no product-level state. |

Inventory consistency: the `GOOGLE_CLIENT_ID`/`SECRET` pair is validator-less in `NBB-208A`'s map because OAuth credentials are consumed per request by `google_auth_service.py` (provider) and then by `google_drive_service.py` (connector). The Google subtree is intentionally split between both roots; `NBB-705C` and the eventual Google-drive connector ticket land the split physically.

## Validator-ownership cross-reference

`NBB-208A` published the authoritative validator-ownership map in the module header of `backend/app/api/settings/api_keys.py` (see "Validator ↔ reload-hook ownership map"). That map names which API-key validator bodies today live under `backend/app/services/app_settings/validation/` and which move under `providers/` when this charter finalizes. This charter does not duplicate the table; it pins the rule.

Providers-owned rows from that map (by `key_id`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `GEMINI_2_5_API_KEY`, `NANO_BANANA_API_KEY`, `VEO_API_KEY`, `PINECONE_API_KEY`, `TAVILY_API_KEY`, `WEBSHARE_API_KEY`, and the observability `OPIK_*` pair (attached to the Claude client).

## Reload semantics

Providers do not self-reload. `settings/` (the `update_api_keys` endpoint in `backend/app/api/settings/api_keys.py`) is the single caller that invokes `env_service.reload_env()` and then per-service `reload_config()` hooks. The sequence is documented in the api_keys.py module header under "Env-reload → service-reload sequence (NBB-208A)" — see there for the canonical ordering.

For Anthropic specifically, `claude_service.reload_config()` (added in `NBB-208A`) re-wraps the client so the Claude API key and the Opik observability attachments pick up new credentials without a process restart. Any future provider that caches configured clients follows the same hook shape; providers with stateless clients (OpenAI embeddings, ElevenLabs, Gemini/Veo/Imagen, Pinecone, Tavily) need no hook.

## Downstream migration tickets

This charter locks the boundary; it does not move code. The mechanical drains live in:

- `NBB-705C` — Drain provider and Anthropic utilities. Splits `utils/claude_parsing_utils.py` into `providers/anthropic/{response_parser,content,usage}.py`; moves `utils/cost_tracking.py`, the API half of `utils/embedding_utils.py`, `utils/rate_limit_utils.py`, and `utils/encoding_utils.py` under `providers/anthropic/`.
- The per-provider migration tickets that follow NBB-705C for OpenAI, ElevenLabs, Google (Imagen/Veo/OAuth half), Pinecone, Tavily, Supabase primitives, YouTube, and the MCP client. None are named here because `NBB-705C` intentionally scopes to the Anthropic family only.

Validator drain for providers-owned API keys (Anthropic, OpenAI, ElevenLabs, Gemini, Veo, Pinecone, Tavily, Webshare, Opik) follows the map in `backend/app/api/settings/api_keys.py` and moves under `providers/` with the validator bodies — `settings/` retains the route and ValidationService facade.

## Cross-reference

- Package-level charter: `backend/app/providers/__init__.py` (NBB-104).
- Connectors counterpart: `backend/app/connectors/CHARTER.md` (NBB-206).
- Validator/reload map: `backend/app/api/settings/api_keys.py` module header (NBB-208A).
- Domain-reviewed storage seam: `backend/app/sources/CHARTER.md` and `backend/supabase/STORAGE_CONTRACTS.md` (NBB-204).
- Tool-schema decision map (which tools stay connector-side vs. domain-side): `docs/tickets/epics/NBB-002.md#nbb-207c`.
- Connector store map (moves `database_connection_service.py`, `mcp_connection_service.py`): `docs/tickets/epics/NBB-002.md#nbb-209e`.
- Tool capability policy consumer: `docs/tickets/epics/NBB-002.md#nbb-202b`.
- Import-direction enforcement: `NBB-704A` (early checks) and `NBB-704B` (rich post-migration).
- Structure rules summary: `STRUCTURE.md` Canonical Backend Roots + Dependency Direction + Providers/Connectors boundary subsection.
