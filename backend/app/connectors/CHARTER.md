# `connectors/` boundary charter (NBB-206)

**Owner:** NBB-206 overlays this charter on top of the package-level import/dependency charter in `backend/app/connectors/__init__.py` (authored by NBB-104). Read the `__init__.py` charter first; this file finalizes the external-edge rules the `__init__.py` defers to NBB-206.

**Scope:** `connectors/<name>/` owns product-level configured external capabilities. A connector wraps one or more provider clients into a user/project-configured integration that chat, studio, or sources can invoke.

Connector territory:
- User/project connector state (stored credentials, selected Notion databases, Jira projects, MCP server URLs, Google Drive tokens, etc.).
- Permission-gated tool schemas exposed to Claude (Notion, Jira, Mixpanel, MCP dynamic tools).
- Chat-invokable adapters that translate Claude tool calls into provider SDK calls.
- Formatting policies that turn provider responses into a shape the chat/studio domains can present.
- Per-connector validation that requires a real product call (not just an SDK ping) — these validator bodies remain under `services/app_settings/validation/` until `NBB-807` moves them beside their connector clients.

## Out of scope

- Raw SDK sprawl. If a module is a thin wrapper over a vendor SDK with no product-level state, it is a provider, not a connector. See `backend/app/providers/CHARTER.md`.
- Domain orchestration. Chat loop logic, source ingestion pipelines, and studio job lifecycles stay in their domain roots. Connectors expose capabilities; they do not orchestrate domains.
- File-format parsing and extraction. PDF, DOCX, PPTX, image, audio, URL, and YouTube format operations are owned by `sources/` per `NBB-401`. A connector may fetch bytes (for example Google Drive download, Jira attachment fetch) and hand them to the `sources/` ingestion public surface; it must not parse file formats itself.
- Studio export/screenshot/media rendering. Those are `studio/`-owned per `NBB-504`–`NBB-507`.
- Domain internals. Connectors must not reach into another domain's internals (no direct `sources/`-internal imports, no direct `chat/`-internal reads). Connector invocations come through domain public surfaces or through the chat tool loop.

`platform/files/` and `providers/files/` are explicitly rejected as default homes. Do not create a generic connector for "file things"; file-format ownership follows `NBB-401`, and connector capabilities are named after their product (Google Drive, Jira, Notion, Mixpanel, Freshdesk, MCP, database).

## Dependency direction (connectors view)

- `connectors/` may import from `providers/`, `auth/`, and `projects/`.
- Domains (`chat/`, `sources/`, `studio/`, `brand/`, `settings/`, `background/`) import connector **public surfaces** only. They must not reach into `connectors/<name>/` internals.
- Connectors must not import from `api/` or from any domain's internals.
- Chat-invokable tool schemas live under `connectors/<name>/tools/`; the chat loop reads them through the loader registry (`NBB-207A`) and executes them through the ToolCapabilityPolicy seam (`NBB-202B`).
- Connector stores (database connection, MCP connection) are connector-owned state per `NBB-209E`. Data-bearing RLS/guard invariants remain governed by `NBB-204`.

Rich import-direction enforcement lands in `NBB-704A` and `NBB-704B`.

## Current-code inventory

Classification of today's `backend/app/services/integrations/` and `backend/app/services/tools/`, plus the former `backend/app/services/data_services/` connector stores, against the providers/connectors split. Target shape is `backend/app/connectors/<name>/`; actual moves land in `NBB-207C` (tool schemas), `NBB-209E` (connector stores), and the per-connector migration tickets that follow.

| Current path | Classification | Rationale |
|---|---|---|
| `services/integrations/knowledge_bases/notion/notion_service.py` | connector | Product-configured Notion integration with cached config and `reload_config()`; tool-visible via `chat_tools/notion_*.json`. Target: `connectors/notion/`. |
| `services/integrations/knowledge_bases/jira/jira_service.py` | connector | Product-configured Jira integration with cached config and `reload_config()`; tool-visible via `chat_tools/jira_*.json`. Target: `connectors/jira/`. |
| `services/integrations/knowledge_bases/mixpanel/mixpanel_service.py` | connector | Product-configured Mixpanel integration with cached config and `reload_config()`; tool-visible via `chat_tools/mixpanel_*.json`. Target: `connectors/mixpanel/`. |
| `services/integrations/knowledge_bases/knowledge_base_service.py` | connector (facade) | Loads tool definitions for configured knowledge-base integrations only; a connector-composition facade, not a raw client. Target lands with the individual connectors or under a small facade module referenced by chat. |
| `services/integrations/freshdesk/freshdesk_service.py` | connector | Product-configured Freshdesk integration with `reload_config()`; matches the `FRESHDESK_*` → `connectors/` row in the NBB-208A validator map. Target: `connectors/freshdesk/`. |
| `services/integrations/freshdesk/freshdesk_sync_service.py` | connector | Freshdesk project-scoped sync behavior; connector-owned. Target: `connectors/freshdesk/`. |
| `services/integrations/google/google_drive_service.py` | connector | Google Drive is a user/project product capability (OAuth-scoped file listing, download, Workspace export). Target: `connectors/google_drive/`. The `google/` subdir splits across roots — OAuth primitive and raw Gemini/Veo clients go to `providers/`, Drive goes to `connectors/`. |
| `services/integrations/mcp/mcp_tool_service.py` | connector | Discovers MCP tools from user connections, namespaces them (`mcp_{slug}_*`), and routes Claude tool calls to the right MCP server. Target: `connectors/mcp/`. |
| `services/data_services/database_connection_service.py` | connector (store) | Per-user database connection credentials. `NBB-209E` moved it to `connectors/database/connection/store.py` as `DatabaseConnectionStore`; `NBB-802` removed the dead residue. |
| `services/data_services/mcp_connection_service.py` | connector (store) | Per-user MCP connection config. `NBB-209E` moved it to `connectors/mcp/connection/store.py` as `McpConnectionStore`; `NBB-802` removed the dead residue. |

Tool-schema rows pulled from the NBB-207C decision map that resolve to connector ownership:

| Tool family | Target |
|---|---|
| `chat_tools/jira_*.json` | `connectors/jira/tools/` |
| `chat_tools/notion_*.json` | `connectors/notion/tools/` |
| `chat_tools/mixpanel_*.json` | `connectors/mixpanel/tools/` |

All other families under `services/tools/` resolve to domain roots (`chat/`, `sources/`, `studio/`) per `NBB-207C`; MCP-sourced tools are registered dynamically at runtime and keep their MCP registration path.

## Tool-schema mapping cross-reference

The authoritative per-family mapping for every static tool JSON file lives in the `NBB-207C` decision map: `docs/tickets/epics/NBB-002.md#nbb-207c`. This charter does not duplicate that table. The rule for connectors: any Claude-visible tool whose execution requires per-user or per-project credentials for an external product (Notion, Jira, Mixpanel, MCP) lives under `connectors/<name>/tools/`. Tools whose execution depends on a domain's data (source search, memory, studio signals, analysis over project-owned data) remain domain-owned even if they call a provider SDK transitively.

Tool moves are gated on `NBB-207A` loader compatibility and executed by `NBB-207C` via `docs/tickets/helpers/json_asset_move.sh` with `move-plan.csv` rows; this charter does not move JSON.

## Connector-store mapping

`NBB-209E` moved the connector stores:

| Former file | Target | Public name |
|---|---|---|
| `services/data_services/database_connection_service.py` | `connectors/database/connection/store.py` | `DatabaseConnectionStore` |
| `services/data_services/mcp_connection_service.py` | `connectors/mcp/connection/store.py` | `McpConnectionStore` |

Schema/RLS implications stay with `NBB-204`; the `*Service → *Store` rename is a refactory `rename_symbol` step recorded in `move-plan.csv` by `NBB-209E`.

## Validator-ownership cross-reference

`NBB-208A` published the authoritative validator-ownership map in the module header of `backend/app/api/settings/api_keys.py` (see "Validator ↔ reload-hook ownership map"). This charter does not duplicate that table. Rows it claims for `connectors/`:

| `key_id(s)` | Today's validator | Reload hook | Target |
|---|---|---|---|
| `NOTION_API_KEY` | `app_settings/validation/notion_validator.py` | `notion_service.reload_config()` | `connectors/notion/` |
| `JIRA_API_KEY` + `JIRA_EMAIL` + `JIRA_CLOUD_ID` | `app_settings/validation/jira_validator.py` | `jira_service.reload_config()` | `connectors/jira/` |
| `FRESHDESK_API_KEY` + `FRESHDESK_DOMAIN` | `app_settings/validation/freshdesk_validator.py` | `freshdesk_service.reload_config()` | `connectors/freshdesk/` |
| `MIXPANEL_SERVICE_ACCOUNT_*` + region/project | `app_settings/validation/mixpanel_validator.py` | `mixpanel_service.reload_config()` | `connectors/mixpanel/` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | accepted-if-present | none (OAuth flow reads env per request) | `connectors/google_drive/` (validator split: OAuth primitive stays provider-side) |

Reload sequencing (`env_service.reload_env()` → per-service `reload_config()`) is owned by `settings/` and documented in the api_keys.py module header; connectors implement the `reload_config()` hook but never self-reload. Any new connector with cached config must implement this hook so `update_api_keys` can call it without a process restart.

## Downstream migration tickets

This charter locks the boundary; it does not move code. Mechanical moves live in:

- `NBB-209E` — Move connector stores. Moves `database_connection_service.py` and `mcp_connection_service.py`; renames `*Service` → `*Store`.
- `NBB-207C` — Define tool-schema ownership map. Moves `chat_tools/jira_*.json`, `chat_tools/notion_*.json`, `chat_tools/mixpanel_*.json` under `connectors/<name>/tools/` once `NBB-207A` loader support lands.
- `NBB-202B` — Create ToolCapabilityPolicy. Classifies MCP, Jira, Notion, Mixpanel, and other connector tools with required permission, capability level, and audit behavior.
- Per-connector migration tickets that follow (not yet named) for Notion, Jira, Mixpanel, Freshdesk, Google Drive, and MCP connector bodies.

## Cross-reference

- Package-level charter: `backend/app/connectors/__init__.py` (NBB-104).
- Providers counterpart: `backend/app/providers/CHARTER.md` (NBB-206).
- Validator/reload map: `backend/app/api/settings/api_keys.py` module header (NBB-208A).
- Tool-schema decision map: `docs/tickets/epics/NBB-002.md#nbb-207c`.
- Connector store decision map: `docs/tickets/epics/NBB-002.md#nbb-209e`.
- Tool capability policy consumer: `docs/tickets/epics/NBB-002.md#nbb-202b`.
- File-format ownership (why connectors do not own file parsing): `docs/tickets/epics/NBB-004.md#nbb-401`.
- Import-direction enforcement: `NBB-704A` (early checks) and `NBB-704B` (rich post-migration).
- Structure rules summary: `STRUCTURE.md` Canonical Backend Roots + Dependency Direction + Providers/Connectors boundary subsection.
