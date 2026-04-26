# `connectors/` boundary charter (NBB-206)

**Owner:** NBB-206 overlays this charter on top of the package-level import/dependency charter in `backend/app/connectors/__init__.py` (authored by NBB-104). Read the `__init__.py` charter first; this file finalizes the external-edge rules the `__init__.py` defers to NBB-206.

**Scope:** `connectors/<name>/` owns product-level configured external capabilities. A connector wraps one or more provider clients into a user/project-configured integration that chat, studio, or sources can invoke.

Connector territory:
- User/project connector state (stored credentials, selected Notion databases, Jira projects, MCP server URLs, Google Drive tokens, etc.).
- Permission-gated tool schemas exposed to Claude (Notion, Jira, Mixpanel, MCP dynamic tools).
- Chat-invokable adapters that translate Claude tool calls into provider SDK calls.
- Formatting policies that turn provider responses into a shape the chat/studio domains can present.
- Per-connector validation that requires a real product call (not just an SDK ping).

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

Documented temporary exception: `connectors/freshdesk/sync.py` still has lazy
progress/cancellation hooks into `background` and `sources` inherited from its
pre-`NBB-807` service location. The architecture checker allowlists those exact
lines until the source-processing move can replace them with an explicit
callback contract.

## Current-code inventory

Classification of connector-owned modules after `NBB-807`, plus the former `backend/app/services/data_services/` connector stores, against the providers/connectors split. Static tool schemas were moved by `NBB-810` and now resolve through domain-owned `tools/` directories.

| Current path | Classification | Rationale |
|---|---|---|
| `connectors/notion/client.py` | connector | Product-configured Notion integration with cached config and `reload_config()`; tool-visible via `chat_tools/notion_*.json`. |
| `connectors/jira/client.py` | connector | Product-configured Jira integration with cached config and `reload_config()`; tool-visible via `chat_tools/jira_*.json`. |
| `connectors/mixpanel/client.py` | connector | Product-configured Mixpanel integration with cached config and `reload_config()`; tool-visible via `chat_tools/mixpanel_*.json`. |
| `connectors/knowledge.py` | connector (facade) | Loads tool definitions for configured knowledge-base integrations only; a connector-composition facade, not a raw client. |
| `connectors/freshdesk/client.py` | connector | Product-configured Freshdesk integration with `reload_config()`; matches the `FRESHDESK_*` → `connectors/` row in the NBB-208A validator map. |
| `connectors/freshdesk/sync.py` | connector | Freshdesk project-scoped sync behavior; connector-owned. |
| `connectors/google_drive/files.py` | connector | Google Drive is a user/project product capability (OAuth-scoped file listing, download, Workspace export). OAuth primitives stay in `providers/google/`. |
| `connectors/mcp/tools.py` | connector | Discovers MCP tools from user connections, namespaces them (`mcp_{slug}_*`), and routes Claude tool calls to the right MCP server. |
| `services/data_services/database_connection_service.py` | connector (store) | Per-user database connection credentials. `NBB-209E` moved it to `connectors/database/connection/store.py` as `DatabaseConnectionStore`; `NBB-802` removed the dead residue. |
| `services/data_services/mcp_connection_service.py` | connector (store) | Per-user MCP connection config. `NBB-209E` moved it to `connectors/mcp/connection/store.py` as `McpConnectionStore`; `NBB-802` removed the dead residue. |

Tool-schema rows pulled from the NBB-207C decision map that resolve to connector ownership:

| Tool family | Target |
|---|---|
| `chat_tools/jira_*.json` | `connectors/jira/tools/` |
| `chat_tools/notion_*.json` | `connectors/notion/tools/` |
| `chat_tools/mixpanel_*.json` | `connectors/mixpanel/tools/` |

All tool-schema families resolve to domain roots (`chat/`, `sources/`, `studio/`, `connectors/`) through the asset registry; MCP-sourced tools are registered dynamically at runtime and keep their MCP registration path.

## Tool-schema mapping cross-reference

The authoritative per-family mapping for every static tool JSON file lives in the `NBB-207C` decision map: `docs/tickets/epics/NBB-002.md#nbb-207c`. This charter does not duplicate that table. The rule for connectors: any Claude-visible tool whose execution requires per-user or per-project credentials for an external product (Notion, Jira, Mixpanel, MCP) lives under `connectors/<name>/tools/`. Tools whose execution depends on a domain's data (source search, memory, studio signals, analysis over project-owned data) remain domain-owned even if they call a provider SDK transitively.

Tool moves were gated on `NBB-207A` loader compatibility and the static connector schemas were completed by `NBB-810`; this charter does not move JSON.

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
| `NOTION_API_KEY` | `connectors/notion/validation.py` | `notion_service.reload_config()` | `connectors/notion/` |
| `JIRA_API_KEY` + `JIRA_EMAIL` + `JIRA_CLOUD_ID` | `connectors/jira/validation.py` | `jira_service.reload_config()` | `connectors/jira/` |
| `FRESHDESK_API_KEY` + `FRESHDESK_DOMAIN` | `connectors/freshdesk/validation.py` | `freshdesk_service.reload_config()` | `connectors/freshdesk/` |
| `MIXPANEL_SERVICE_ACCOUNT_*` + region/project | `connectors/mixpanel/validation.py` | `mixpanel_service.reload_config()` | `connectors/mixpanel/` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | accepted-if-present | none (OAuth flow reads env per request) | `connectors/google_drive/` (validator split: OAuth primitive stays provider-side) |

Reload sequencing (`env_service.reload_env()` → per-service `reload_config()`) is owned by `settings/` and documented in the api_keys.py module header; connectors implement the `reload_config()` hook but never self-reload. Any new connector with cached config must implement this hook so `update_api_keys` can call it without a process restart.

## Downstream migration tickets

This charter locks the boundary; it does not move code. Mechanical moves live in:

- `NBB-209E` — Move connector stores. Moves `database_connection_service.py` and `mcp_connection_service.py`; renames `*Service` → `*Store`.
- `NBB-207C` — Define tool-schema ownership map. Moves `chat_tools/jira_*.json`, `chat_tools/notion_*.json`, `chat_tools/mixpanel_*.json` under `connectors/<name>/tools/` once `NBB-207A` loader support lands.
- `NBB-202B` — Create ToolCapabilityPolicy. Classifies MCP, Jira, Notion, Mixpanel, and other connector tools with required permission, capability level, and audit behavior.
- `NBB-807` — Move Notion, Jira, Mixpanel, Freshdesk, Google Drive, MCP tool routing, the knowledge-base facade, and connector validators into `connectors/`.

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
