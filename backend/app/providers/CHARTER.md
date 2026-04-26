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
- Domain-reviewed provider seam: `sources/CHARTER.md` pins `providers/supabase/storage.py` as the single path builder for the `raw-files`, `processed-files`, and `chunks` buckets. Do not introduce sibling path builders; the seam crosses the boundary by design and is reviewed under `NBB-204`.

Rich import-direction enforcement lands in `NBB-704A` and `NBB-704B`.

## Documented exceptions (NBB-704B)

`NBB-704B` accepts five inherited providers→domain imports under `providers/anthropic/` and encodes them line-by-line in `backend/scripts/verify_architecture.py` as `INHERITED_PROVIDER_VIOLATIONS`. These are not regressions and do not weaken the leaf rule above; they are observability hooks that legitimately depend on user/project/chat ownership, and the cycle is broken at runtime by lazy imports inside helper functions.

| File and line | Imports | Why it stays |
|---|---|---|
| `backend/app/providers/anthropic/cost.py:76` | `app.projects.store.project_service` | Project cost tracking writes through the project ownership store; `_get_project_service` lazily imports inside a helper to break the runtime cycle. |
| `backend/app/providers/anthropic/cost.py:82` | `app.chat.store.chat_service` | Per-chat cost mirroring (NBB-209A schema) writes through the chat store; lazy-imported alongside the project service. |
| `backend/app/providers/anthropic/cost.py:300` | `app.auth.user.store.get_user_service` | Spending-limit lookup reads `users.cost_limit` and `users.period_*` columns owned by `auth/`; lazy-imported inside `check_user_spending_limit`. |
| `backend/app/providers/anthropic/cost.py:357` | `app.auth.user.store.get_user_service` | Period-spend write companion to the lookup above; lazy-imported inside `record_user_period_spend`. |
| `backend/app/providers/anthropic/token_count.py:12` | `app.sources.tokens.count_tokens` | tiktoken fallback when the Anthropic count-tokens API call fails; the fallback is the same helper `sources/` uses for chunking, so duplicating it here would diverge the two estimators. Eager import is acceptable because `sources.tokens` does not import back into `providers/`. |

NBB-705C reviewer confirmed the `cost.py` imports are byte-identical to the pre-move `utils/cost_tracking.py` source. The allowlist is keyed on `(rel_path, lineno, target_root)`; if any of these helpers move to a new line, the verifier surfaces the move and the entry must be re-confirmed under the same rationale.

## Current-code inventory

Classification of provider client modules after `NBB-806`. Connector clients moved under `backend/app/connectors/` in `NBB-807` and are intentionally outside this inventory.

| Current path | Classification | Rationale |
|---|---|---|
| `providers/anthropic/messages.py` | provider | Raw Anthropic Messages API client; `NBB-705C` drains Claude parsing/cost/rate helpers alongside it into `providers/anthropic/`. |
| `providers/openai/embeddings.py` | provider | Raw OpenAI embeddings client; stateless, no product orchestration. |
| `providers/elevenlabs/audio.py` | provider | ElevenLabs Scribe v1 transcription SDK call. |
| `providers/elevenlabs/transcription.py` | provider | ElevenLabs streaming-transcription token minting (runtime IO primitive). |
| `providers/elevenlabs/tts.py` | provider | ElevenLabs TTS SDK call. |
| `providers/pinecone/index.py` | provider | Vector DB client + index lifecycle; auto-index creation is a provider concern. |
| `providers/tavily/search.py` | provider | Raw Tavily search SDK call. |
| `providers/supabase/client.py` | provider | Shared Supabase service-role client factory. |
| `providers/supabase/auth.py` | provider | Supabase auth SDK wrapper (identity primitives). |
| `providers/supabase/storage.py` | provider (domain-reviewed seam) | Bucket path builder and upload/download primitive; `sources/CHARTER.md` names it as the single writer for source buckets. |
| `providers/google/auth.py` | provider | Google OAuth 2.0 token exchange and refresh — a protocol primitive separate from any Google product capability. |
| `providers/google/imagen.py` | provider | Raw Gemini Pro Image model client. Matches the `GEMINI_*`/`NANO_BANANA_API_KEY` → `providers/` rows in `NBB-208A`. |
| `providers/google/veo.py` | provider | Raw Veo API client. Matches the `VEO_API_KEY` → `providers/` row in `NBB-208A`. |
| `providers/youtube/transcript.py` | provider | Provider-neutral fetch primitive (`youtube-transcript-api`) consumed directly by `sources/`; no product/connector state. |
| `providers/mcp/client.py` | provider | SSE/stdio transport wrapper around the MCP SDK; no product-level state. |

Inventory consistency: the `GOOGLE_CLIENT_ID`/`SECRET` pair is validator-less in `NBB-208A`'s map because OAuth credentials are consumed per request by `providers/google/auth.py` and then by `connectors/google_drive/files.py`.

## Validator-ownership cross-reference

`NBB-208A` published the authoritative validator-ownership map in the module header of `backend/app/api/settings/api_keys.py` (see "Validator ↔ reload-hook ownership map"). `NBB-806` reconciled that map so provider validator bodies now point at their current `providers/` homes. This charter does not duplicate the table; it pins the rule.

Providers-owned rows from that map (by `key_id`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `GEMINI_2_5_API_KEY`, `NANO_BANANA_API_KEY`, `VEO_API_KEY`, `PINECONE_API_KEY`, `TAVILY_API_KEY`, `WEBSHARE_API_KEY`, and the observability `OPIK_*` pair (attached to the Claude client).

## Reload semantics

Providers do not self-reload. `settings/` (the `update_api_keys` endpoint in `backend/app/api/settings/api_keys.py`) is the single caller that invokes `env_service.reload_env()` and then per-service `reload_config()` hooks. The sequence is documented in the api_keys.py module header under "Env-reload → service-reload sequence (NBB-208A)" — see there for the canonical ordering.

For Anthropic specifically, `claude_service.reload_config()` (added in `NBB-208A`) re-wraps the client so the Claude API key and the Opik observability attachments pick up new credentials without a process restart. Any future provider that caches configured clients follows the same hook shape; providers with stateless clients (OpenAI embeddings, ElevenLabs, Gemini/Veo/Imagen, Pinecone, Tavily) need no hook.

## Downstream migration tickets

This charter locks the boundary. The physical provider-client drain landed in `NBB-806`; connector moves remain follow-up work.

- `NBB-705C` — Drain provider and Anthropic utilities. Splits `utils/claude_parsing_utils.py` into `providers/anthropic/{response_parser,content,usage}.py`; moves `utils/cost_tracking.py`, the API half of `utils/embedding_utils.py`, `utils/rate_limit_utils.py`, and `utils/encoding_utils.py` under `providers/anthropic/`.
- `NBB-806` — moved OpenAI, ElevenLabs, Google (Imagen/Veo/OAuth half), Pinecone, Tavily, Supabase primitives, YouTube, MCP transport, and provider-owned validators under `providers/`.

Provider-owned API-key validators (Anthropic, OpenAI, ElevenLabs, Gemini, Nano Banana, Veo, Pinecone, Tavily, Opik) live under their matching `providers/` modules. `settings/` retains the route and validation dispatcher in `app.settings.validation`.

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
