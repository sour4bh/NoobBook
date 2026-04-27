# `backend/supabase/migrations/` owner and contract index

**Owner (NBB-204):** Backend data-contracts lane. Owns the schema/RLS/storage contract inventory that domain store moves (`NBB-209A`-`E`) and background/studio ownership (`NBB-210`, `NBB-501B`) must consult before touching a table or bucket.

**Validation approach:** any new migration must cite (a) which tables/buckets it touches, (b) the RLS or backend-guard invariant it preserves or changes, (c) the serving route(s) that read/write the affected data. Reviewer cross-checks each against `../STORAGE_CONTRACTS.md` and the data-bearing `CHARTER.md` of the owning domain root before merge.

**Out of scope for NBB-204:** rewriting any migration SQL. Schema evolution is owned by the ticket that proposes the change and is not moved by this ticket.

## Rules

1. Migrations land in numeric order and are never edited once merged. Additive migrations only.
2. Every new migration must update one of:
   - `../STORAGE_CONTRACTS.md` (if it changes a bucket, object path, or storage policy), or
   - a data-bearing root `CHARTER.md` (if it changes a table the root owns), or
   - both.
3. An RLS change must either preserve the `auth.uid()`-based invariants below or explicitly state why the SaaS path and the self-hosted path diverge.
4. `backend/supabase/init.sql` is the self-hosted Docker bootstrap. It is **not** a migration. See the "Two deployment modes" note below before editing it.

## Migration index

| File | Adds/changes | RLS touched? | Storage touched? | Primary consumer docs |
|---|---|---|---|---|
| `00001_initial_schema.sql` | `users`, `projects`, `sources`, `chats`, `messages`, `studio_signals`, `chunks`, `background_tasks`, cost JSONB on `projects`, `updated_at` trigger, `update_project_last_accessed()` | No (RLS enabled in 00003) | No | `backend/app/projects/CHARTER.md`, `backend/app/sources/CHARTER.md`, `backend/app/chat/CHARTER.md`, `backend/app/studio/CHARTER.md`, `backend/app/background/CHARTER.md` |
| `00002_storage_buckets.sql` | Buckets `raw-files`, `processed-files`, `chunks`, `studio-outputs`; `storage.objects` policies; `generate_*_path()` helpers | Storage policies only | Yes (four buckets) | `backend/supabase/STORAGE_CONTRACTS.md`, `backend/app/sources/CHARTER.md`, `backend/app/studio/CHARTER.md` |
| `00003_rls_policies.sql` | `ENABLE ROW LEVEL SECURITY` + policies for `users`, `projects`, `sources`, `chats`, `messages`, `studio_signals`, `chunks`, `background_tasks` | Yes (all core tables) | No | Every data-bearing root `CHARTER.md` |
| `00004_functions_triggers.sql` | Helper triggers and functions | No | No | n/a |
| `00005_enable_pgvector.sql` | `pgvector` extension | No | No | `backend/app/sources/CHARTER.md` (future embedding column) |
| `00006_user_roles.sql` | `user_role` enum, `users.role`, `project_members` table + RLS + helper functions (`user_has_project_access`, `user_is_project_owner`, `user_is_admin`) | Yes (`project_members`) | No | `backend/app/projects/CHARTER.md` (project access model) |
| `00007_brand_assets.sql` | `brand_assets`, `brand_config` tables (project-scoped initially) + RLS | Yes | Bucket `brand-assets` documented under NBB-204 inventory | `backend/app/brand/CHARTER.md` |
| `00008_google_oauth_tokens.sql` | `users.google_tokens` JSONB, `is_google_connected()` | No new policy (inherits `users`) | No | `backend/app/connectors/` (NBB-206 scope) |
| `00009_studio_jobs.sql` | `studio_jobs` table | **No RLS enabled on this table.** Access enforced by backend project guard (see below). | Serves studio bucket paths | `backend/app/studio/CHARTER.md` |
| `00010_brand_to_user_level.sql` | Moves `brand_assets`/`brand_config` from project-scoped to user-scoped; replaces RLS; updates `generate_brand_asset_path()` to `{user_id}/brand/{asset_id}/{filename}` | Yes (replaces policies) | Yes (brand object path) | `backend/app/brand/CHARTER.md`, `backend/supabase/STORAGE_CONTRACTS.md` |
| `00011_database_visible_to_all.sql` | `database_connections.visible_to_all` | Account-level table; no per-row RLS | No | `backend/app/connectors/` (NBB-206) |
| `00012_background_tasks_started_at.sql` | `background_tasks.started_at` | Existing RLS preserved | No | `backend/app/background/CHARTER.md` |
| `00013_chat_selected_sources.sql` | `chats.selected_source_ids UUID[]` | Existing `chats` RLS preserved | No | `backend/app/chat/CHARTER.md` |
| `00014_mcp_connections.sql` | `mcp_connections`, `mcp_connection_users` | **No RLS enabled.** Account-level store gated by backend guards. | No | `backend/app/connectors/` (NBB-206) |
| `00015_mcp_stdio_and_tools.sql` | `mcp_connections.stdio_config`, `tools_enabled`, `cached_tools`, `tools_cached_at` | No | No | `backend/app/connectors/` (NBB-206) |
| `00016_freshdesk_tickets.sql` | `freshdesk_tickets` (per-source initially) | **No RLS enabled.** Backend guard only. | No | `backend/app/sources/CHARTER.md` (analysis slice) |
| `00017_freshdesk_global_tickets.sql` | Moves `freshdesk_tickets` to global keyed by `ticket_id` | **No RLS enabled.** Data intentionally shared across users in this deployment. | No | `backend/app/sources/CHARTER.md` |
| `00018_chat_costs.sql` | `chats.costs` JSONB mirroring `projects.costs` | Existing `chats` RLS preserved | No | `backend/app/chat/CHARTER.md`, `backend/app/projects/CHARTER.md` |
| `00019_user_permissions.sql` | `users.permissions` JSONB (NULL = all enabled) | Inherits `users` RLS | No | `backend/app/auth/` charter (NBB-104 owns `users` table; NBB-202A owns permission evaluation) |
| `00020_background_task_ownership.sql` | `background_tasks.project_id`, `background_tasks.user_id`, backfill, helper indexes, ownership policies | Yes (`background_tasks`) | No | `backend/app/background/CHARTER.md` |
| `00021_storage_owner_paths.sql` | Owner-prefix storage path backfill, first-folder storage policies, updated path helper functions | Storage policies only | Yes (raw, processed, chunks, studio, brand buckets) | `backend/supabase/STORAGE_CONTRACTS.md`, `backend/app/sources/CHARTER.md`, `backend/app/studio/CHARTER.md`, `backend/app/brand/CHARTER.md` |
| `00022_oauth_state_nonces.sql` | `oauth_states` one-time nonce table for provider OAuth callbacks | Yes (`oauth_states`) | No | `backend/app/providers/google/auth.py`, `backend/app/api/google/oauth.py` |
| `00023_workspace_membership.sql` | `workspaces`, `workspace_members`, private `project_members` roles, `workspace_invites`, `workspace_provider_secrets`, `projects.workspace_id`, workspace-aware storage paths and helpers | Yes (workspace/project membership + project-owned tables) | Yes (raw, processed, chunks, studio buckets) | `docs/tickets/epics/NBB-010.md`, `backend/supabase/STORAGE_CONTRACTS.md`, `backend/app/projects/CHARTER.md` |
| `00024_workspace_brand_settings.sql` | Moves `brand_assets`/`brand_config` from user-scoped to workspace-scoped; replaces RLS; updates `generate_brand_asset_path()` to `{workspace_id}/brand/{asset_id}/{filename}` | Yes (workspace brand tables + brand bucket policies) | Yes (brand bucket) | `backend/app/brand/CHARTER.md`, `backend/supabase/STORAGE_CONTRACTS.md` |

## Two deployment modes (important for validation)

NoobBook ships against two different enforcement stacks. The inventory below assumes deployment awareness:

1. **Supabase-hosted (multi-user, SaaS) mode** uses the migrations in this directory as-is. RLS policies in `00003` and `00006`/`00007`/`00010` are the primary access guard for user-scoped tables. `auth.uid()` returns the authenticated user's id.
2. **Self-hosted Docker / single-user mode** applies `backend/supabase/init.sql` on first boot. That file creates the same tables and, after `NBB-010`, the same workspace/project-aware storage policy shape for project-owned buckets. It does **not** enable RLS on the core tables. In this mode the backend project guard (`@before_request` enforce in `backend/app/__init__.py` calling `project_service.has_project_access()`) is the only table access barrier.

Both modes are live. Migration changes must keep both modes consistent or state explicitly which mode is affected.

**Auth-required precondition.** The `@before_request` project guard in `backend/app/__init__.py::enforce_auth` runs only when `is_auth_required()` is True. Self-hosted single-user deployments with auth disabled have no per-request access barrier by design; cross-user isolation does not apply because there is exactly one user. Any "backend guard" claim below presumes an auth-required deployment (hosted or self-hosted multi-user).

## Project-owned table access model (NBB-204 inventory)

For every project-owned table, "Enforced by" names the guard actually rejecting a cross-user read/write today. "Both" means the guard is defence-in-depth.

| Table | Ownership | Enforced by (hosted mode) | Enforced by (self-hosted mode) | Touched by migration |
|---|---|---|---|---|
| `projects` | `projects/` | RLS (`user_has_project_access(id, auth.uid())`) + backend guard | Backend guard (`has_project_access`) | 00001, 00003, 00023 |
| `sources` | `sources/` | RLS (`user_has_project_access(project_id, auth.uid())`) + backend guard | Backend guard (route-level project_id path) | 00001, 00003, 00023 |
| `chunks` | `sources/` (indexing slice) | RLS (source -> explicit project membership) + backend guard | Backend guard | 00001, 00003, 00023 |
| `chats` | `chat/` | RLS (`user_has_project_access(project_id, auth.uid())`) + backend guard | Backend guard | 00001, 00003, 00013 (selected_source_ids), 00018 (costs), 00023 |
| `messages` | `chat/` | RLS (chat -> explicit project membership) + backend guard | Backend guard | 00001, 00003, 00023 |
| `studio_signals` | `studio/` (signal slice) | RLS (chat -> project ownership subquery) + backend guard | Backend guard | 00001, 00003 |
| `studio_jobs` | `studio/` | **Backend guard only.** No RLS enabled by 00009. | Backend guard | 00009 |
| `background_tasks` | `background/` | RLS (polymorphic target_type -> project ownership) + backend guard | Backend guard | 00001, 00003, 00012 |
| `brand_assets` | `brand/` | RLS (`user_has_workspace_access` read, `user_can_manage_workspace` write after 00024) | Backend workspace guard | 00007, 00010, 00024 |
| `brand_config` | `brand/` | RLS (`user_has_workspace_access` read, `user_can_manage_workspace` write after 00024) | Backend workspace guard | 00007, 00010, 00024 |
| `project_members` | `projects/` (membership) | RLS (project owner manages; project members can view) | Backend guard | 00006, 00023 |

## Workspace-scoped table access model

| Table | Ownership | Enforced by (hosted mode) | Enforced by (self-hosted mode) | Touched by migration |
|---|---|---|---|---|
| `workspaces` | `workspaces/` (NBB-010 owner) | RLS through `workspace_members` | Backend guard/API membership checks | 00023 |
| `workspace_members` | `workspaces/` | RLS (`owner/admin` manages; members view) | Backend guard/API membership checks | 00023 |
| `workspace_invites` | `workspaces/` | RLS (`owner/admin` manages); invite acceptance uses signed token through backend | Backend guard/API membership checks | 00023 |
| `workspace_provider_secrets` | `settings/` + `providers/` | RLS (`owner/admin` manages) plus backend encryption | Backend guard/API membership checks | 00023 |

## User-scoped table access model

| Table | Ownership | Enforced by (hosted mode) | Enforced by (self-hosted mode) | Touched by migration |
|---|---|---|---|---|
| `users` | `auth/` | RLS (`auth.uid() = id`); INSERT handled by Supabase Auth | Backend auth + admin bootstrap | 00001, 00003, 00006 (role), 00008 (google_tokens), 00019 (permissions) |
| `oauth_states` | `providers/google/` + `api/google/` | RLS (`user_id = auth.uid()`) for user-side insert/read; backend service role consumes callback nonces | Backend service role consumes callback nonces | 00022 |

## Account-level store access model (non-project-scoped)

These stores are explicitly shared within the deployment. Do not add per-user RLS without a ticket that amends the product decision.

| Table | Ownership target | Access model | Touched by migration |
|---|---|---|---|
| `database_connections`, `database_connection_users` | `connectors/` (NBB-206 owner) | No RLS. Backend guards check owner/admin role plus `visible_to_all` or membership. | 00011, init.sql |
| `mcp_connections`, `mcp_connection_users` | `connectors/` (NBB-206 owner) | No RLS. Same backend-guard model as database connections. | 00014, 00015 |
| `freshdesk_tickets` | `sources/analysis/freshdesk/` (NBB-403 owner) | No RLS. Global per-deployment; accessed via source/project routes that already ran the project guard before issuing the analysis query. | 00016, 00017 |

## JSONB contract inventory (NBB-204 names these; field shapes belong to NBB-205)

| JSONB column | Table | Owner doc | Shape contract owner |
|---|---|---|---|
| `projects.costs` | `projects` | `backend/app/projects/CHARTER.md` | NBB-205 (cross-stack contract) |
| `chats.costs` | `chats` | `backend/app/chat/CHARTER.md` | NBB-205 |
| `messages.content` | `messages` | `backend/app/chat/CHARTER.md` | NBB-205 |
| `studio_signals.direction`, `studio_signals.source_ids` | `studio_signals` | `backend/app/studio/CHARTER.md` | NBB-205 |
| `studio_jobs.job_data` | `studio_jobs` | `backend/app/studio/CHARTER.md` | NBB-205 |
| `sources.embedding_info`, `sources.summary_info` | `sources` | `backend/app/sources/CHARTER.md` | NBB-205 |
| `brand_config.colors`, `...typography`, `...spacing`, `...guidelines`, `...best_practices`, `...voice`, `...feature_settings` | `brand_config` | `backend/app/brand/CHARTER.md` | NBB-205 |
| `brand_assets.metadata` | `brand_assets` | `backend/app/brand/CHARTER.md` | NBB-205 |
| `users.memory`, `users.settings`, `users.google_tokens`, `users.permissions` | `users` | `backend/app/auth/` (NBB-104 charter) + `backend/app/connectors/` for google_tokens (NBB-206) | NBB-205 (permissions + cost shapes) |
| `mcp_connections.auth_config`, `stdio_config`, `cached_tools` | `mcp_connections` | connector charter (NBB-206) | NBB-205 |

## Cross-reference

- Storage bucket and object-path inventory: `../STORAGE_CONTRACTS.md`.
- Cross-user access smoke checklist: `../../docs/tickets/checklists/data_access_smoke.md`.
- Test implementation for the checklist: `NBB-107` (auth/permissions), `NBB-702` (sources/citations), `NBB-703` (studio jobs/background). This ticket owns the inventory, not the tests.
