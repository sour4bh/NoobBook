# `studio/` per-item layer map (NBB-502)

**Status:** Locked for `NBB-503` pilot and `NBB-504`–`NBB-507` category migrations. Builds on `TAXONOMY.md` (NBB-501A) and `REGISTRY.md` (NBB-501B). Item and category names come verbatim from `TAXONOMY.md`; current-file paths come verbatim from `REGISTRY.md`.

**Authority:** `TAXONOMY.md` locks categories/items. `REGISTRY.md` locks current-vs-target paths per item. This file locks the five-file per-item runtime shape, the executable naming rule, and the status/progress/result contract links. This file does not move code, JSON, or tests; category migrations land the physical moves.

**Consumers:**
- `NBB-503` (pilot): first end-to-end vertical slice against the shape below.
- `NBB-504`–`NBB-507` (migrations): apply the shape per item. `NBB-705D` drains any remaining studio utilities under this shape.

## Layer definitions

Every studio item directory uses these file names when the layer exists. Create files only for layers that exist in that item's behavior.

| Layer | Canonical file | Role | Replaces |
|---|---|---|---|
| Core operation | `<item>/<verb>.py` | Core domain operation (planning, composition, generation). Domain verb is fixed per item in the table below. | Legacy service/agent modules. |
| Background job wiring | `<item>/job.py` | Background job entry point, status/progress transitions, and `studio_jobs` lifecycle wiring. | Legacy per-item job modules. |
| Sync tool dispatch | `<item>/tool.py` | Per-tool sync dispatch for the Claude agentic loop. | Legacy tool-executor modules. |
| Background orchestration | `<item>/run.py` | Background agentic orchestration (multi-step loops, phase control). | Legacy agent-executor modules. |
| Wire shapes | `<item>/schema.py` | Item-local request/result/progress shapes tied to Contract 13 (studio job status/progress/result). | New local contract file per `NBB-205`. |

## Executable naming rule

| Migrated executable shape | Entry point rule |
|---|---|
| Multi-tool `<item>/tool.py` router | Export `dispatch(...)`. Do not keep `execute_tool(...)`. |
| Single-action tool module | Export the domain verb directly (`search`, `store`, `emit`, `analyze`, `fetch`, `research`, etc.). Do not export `execute_tool(...)`. |
| Studio signal executor | `studio/signal.py::emit(...)`. Studio-level, not item-specific. |

## Core-operation verb table

Per-item verb is fixed; migrators must not rename.

| Item path | Core operation file |
|---|---|
| `documents/blog/` | `write.py` |
| `documents/business_report/` | `write.py` |
| `documents/prd/` | `write.py` |
| `documents/presentation/` | `compose.py` |
| `marketing/ad/` | `create.py` |
| `marketing/email/` | `write.py` |
| `marketing/infographic/` | `create.py` |
| `marketing/strategy/` | `plan.py` |
| `marketing/social_post/` | `write.py` |
| `design/component/` | `build.py` |
| `design/flow_diagram/` | `build.py` |
| `design/logo/` | `create.py` |
| `design/website/` | `build.py` |
| `design/wireframe/` | `draw.py` |
| `learning/flash_card/` | `create.py` |
| `learning/mind_map/` | `build.py` |
| `learning/quiz/` | `create.py` |
| `media/audio/` | `generate.py` |
| `media/video/` | `generate.py` |

Row count: 19. Matches `TAXONOMY.md` (5 categories × 19 items) and the locked filenames in `docs/tickets/epics/NBB-005.md#nbb-502`.

## Layer constraints

- Do not merge `job.py` into `run.py`.
- Do not preserve `<item>_service.py`, `<item>_tool_executor.py`, `<item>_agent_executor.py`, or `jobs/<item>_jobs.py` as renamed files in the new item path.
- Do not preserve `execute_tool(...)` as the entrypoint name in migrated studio tool modules.
- Create files only for existing layers; no placeholder files.
- Absent layers are explicit `none` in the per-item map below, not omitted rows.

## Per-item layer presence map

Source paths come from `REGISTRY.md`. `none` means the layer is intentionally absent for that item at base commit; migrators must not synthesize a placeholder file. Every row ties to Contract 13 (studio job status/progress/result), Contract 7 (`studio_signals`), Contract 10 (background-task polling) and `backend/app/background/tasks.py` (NBB-210 background ownership).

### Documents

#### `documents/blog/` → `write.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `write.py` (core) | `backend/app/studio/documents/blog/write.py` |
| `job.py` | `backend/app/studio/documents/blog/job.py` |
| `tool.py` | `backend/app/studio/documents/blog/tool.py` |
| `run.py` | `backend/app/studio/documents/blog/run.py` |
| `schema.py` | none (new local contract file; lands in NBB-504 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `documents/business_report/` → `write.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `write.py` (core) | `backend/app/studio/documents/business_report/write.py` |
| `job.py` | `backend/app/studio/documents/business_report/job.py` |
| `tool.py` | `backend/app/studio/documents/business_report/tool.py` |
| `run.py` | `backend/app/studio/documents/business_report/run.py` |
| `schema.py` | none (new local contract file; lands in NBB-504 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `documents/prd/` → `write.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `write.py` (core) | `backend/app/studio/documents/prd/write.py` |
| `job.py` | `backend/app/studio/documents/prd/job.py` |
| `tool.py` | `backend/app/studio/documents/prd/tool.py` |
| `run.py` | none (prd uses `is_last_section` termination inside `tool.py`; no separate agent orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-504 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `documents/presentation/` → `compose.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `compose.py` (core) | `backend/app/studio/documents/presentation/compose.py` |
| `job.py` | `backend/app/studio/documents/presentation/job.py` |
| `tool.py` | `backend/app/studio/documents/presentation/tool.py` |
| `run.py` | `backend/app/studio/documents/presentation/run.py` |
| `schema.py` | none (new local contract file; lands in NBB-504 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

### Marketing

#### `marketing/ad/` → `create.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `create.py` (core) | `backend/app/studio/marketing/ad/create.py` |
| `job.py` | `backend/app/studio/marketing/ad/job.py` |
| `tool.py` | none (image-first service; no Claude agentic tool loop) |
| `run.py` | none (image-first service; no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-505 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `marketing/email/` → `write.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `write.py` (core) | `backend/app/studio/marketing/email/write.py` |
| `job.py` | `backend/app/studio/marketing/email/job.py` |
| `tool.py` | `backend/app/studio/marketing/email/tool.py` |
| `run.py` | `backend/app/studio/marketing/email/run.py` |
| `schema.py` | none (new local contract file; lands in NBB-505 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `marketing/infographic/` → `create.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `create.py` (core) | `backend/app/studio/marketing/infographic/create.py` |
| `job.py` | `backend/app/studio/marketing/infographic/job.py` |
| `tool.py` | none (image-first service; no Claude agentic tool loop) |
| `run.py` | none (image-first service; no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-505 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `marketing/strategy/` → `plan.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `plan.py` (core) | `backend/app/studio/marketing/strategy/plan.py` |
| `job.py` | `backend/app/studio/marketing/strategy/job.py` |
| `tool.py` | `backend/app/studio/marketing/strategy/tool.py` |
| `run.py` | none (marketing_strategy has no separate agent executor; tool executor drives the loop) |
| `schema.py` | none (new local contract file; lands in NBB-505 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `marketing/social_post/` → `write.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `write.py` (core) | `backend/app/studio/marketing/social_post/write.py` |
| `job.py` | `backend/app/studio/marketing/social_post/job.py` |
| `tool.py` | none (image-first + templated text; no Claude agentic tool loop) |
| `run.py` | none (image-first + templated text; no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-505 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

### Design

#### `design/component/` → `build.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `build.py` (core) | `backend/app/studio/design/component/build.py` |
| `job.py` | `backend/app/studio/design/component/job.py` |
| `tool.py` | `backend/app/studio/design/component/tool.py` |
| `run.py` | `backend/app/studio/design/component/run.py` |
| `schema.py` | none (new local contract file; lands in NBB-506 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `design/flow_diagram/` → `build.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `build.py` (core) | `backend/app/studio/design/flow_diagram/build.py` |
| `job.py` | `backend/app/studio/design/flow_diagram/job.py` |
| `tool.py` | none (single Claude call with `flow_diagram_tool.json`; no tool executor module exists today) |
| `run.py` | none (no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-506 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `design/logo/` → `create.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `create.py` (core) | none (reserved slot; no logo-generation service exists today) |
| `job.py` | none (reserved) |
| `tool.py` | none (reserved) |
| `run.py` | none (reserved) |
| `schema.py` | none (reserved) |
| Contracts | n/a (no item yet) |
| Background | n/a (no item yet) |

Reserved slot only. `api/studio/logo_utils.py` is studio-level brand-asset resolution support, not logo generation — see "Studio-level modules (not items)" below.

#### `design/website/` → `build.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `build.py` (core) | `backend/app/studio/design/website/build.py` |
| `job.py` | `backend/app/studio/design/website/job.py` |
| `tool.py` | `backend/app/studio/design/website/tool.py` |
| `run.py` | `backend/app/studio/design/website/run.py` |
| `schema.py` | none (new local contract file; lands in NBB-506 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `design/wireframe/` → `draw.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `draw.py` (core) | `backend/app/studio/design/wireframe/draw.py` |
| `job.py` | `backend/app/studio/design/wireframe/job.py` |
| `tool.py` | `backend/app/studio/design/wireframe/tool.py` |
| `run.py` | none (wireframe has no separate agent executor) |
| `schema.py` | none (new local contract file; lands in NBB-506 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

### Learning

#### `learning/flash_card/` → `create.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `create.py` (core) | `backend/app/studio/learning/flash_card/create.py` |
| `job.py` | `backend/app/studio/learning/flash_card/job.py` |
| `tool.py` | none (single Claude call with `flash_cards_tool.json`; no tool executor module exists today) |
| `run.py` | none (no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-507 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `learning/mind_map/` → `build.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `build.py` (core) | `backend/app/studio/learning/mind_map/build.py` |
| `job.py` | `backend/app/studio/learning/mind_map/job.py` |
| `tool.py` | none (single Claude call with `mind_map_tool.json`; no tool executor module exists today) |
| `run.py` | none (no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-507 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `learning/quiz/` → `create.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `create.py` (core) | `backend/app/studio/learning/quiz/create.py` |
| `job.py` | `backend/app/studio/learning/quiz/job.py` |
| `tool.py` | none (single Claude call with `quiz_tool.json`; no tool executor module exists today) |
| `run.py` | none (no multi-step background orchestration) |
| `schema.py` | none (new local contract file; lands in NBB-507 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

### Media

#### `media/audio/` → `generate.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `generate.py` (core) | `backend/app/studio/media/audio/generate.py` |
| `job.py` | `backend/app/studio/media/audio/job.py` |
| `tool.py` | `backend/app/studio/media/audio/tool.py` (handles `write_script_section` — studio-owned; invokes sources-owned `read_source_content` through sources public surface) |
| `run.py` | none (audio uses the tool-executor agentic loop directly) |
| `schema.py` | none (new local contract file; lands in NBB-507 tied to Contract 13) |
| Contracts | Contract 13; Contract 7; Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

#### `media/video/` → `generate.py`

| Layer | Current (from REGISTRY) |
|---|---|
| `generate.py` (core) | `backend/app/studio/media/video/generate.py` |
| `job.py` | `backend/app/studio/media/video/job.py` |
| `tool.py` | `backend/app/studio/media/video/tool.py` (studio-signal router: creates job + launches background generation from a chat `studio_signal`) |
| `run.py` | none (video is a single-call generator, not an agentic loop) |
| `schema.py` | none (new local contract file; lands in NBB-507 tied to Contract 13) |
| Contracts | Contract 13; Contract 7 (studio_signal entrypoint); Contract 10 |
| Background | `backend/app/background/tasks.py` (NBB-210) |

Per-item row count: 19. Matches `TAXONOMY.md`. Every row carries explicit values for all five layers.

## Studio-level modules (not items)

These modules live in the studio domain but are not item-owned. `REGISTRY.md` enumerates their current paths; this file fixes their layer placement.

| Current module | Role | Target under `studio/` |
|---|---|---|
| `backend/app/api/studio/__init__.py` | Studio blueprint registrar and project-access guard. | Route file; route movement deferred under `D-001`. |
| `backend/app/api/studio/logo_utils.py` | Brand-asset resolution helper consumed by `ads.py`, `blogs.py`, `infographics.py`, `social_posts.py`. | Studio-level brand-asset resolution support. Final placement (studio helper vs brand public surface) is decided by `NBB-506`; this file is not logo generation and is not item-owned. |
| `backend/app/services/studio_services/studio_index_service.py` | Generic CRUD for the `studio_jobs` table; per-item `create_job`/`update_job`/`get_job`/`list_jobs`/`delete_job` wrappers. Writer of record for Contract 13. | Studio-level job index module (owned by `studio/` at studio-level, not inside an item directory). `NBB-210` owns `background/tasks.py` and must not be duplicated. |
| Removed `studio_processing/` package | Empty package deleted during cleanup. | No runtime surface. |
| Per-item job modules | Per-item `job.py` wiring lives in the item directories listed above. | No forwarding jobs package remains. |
| `backend/app/studio/signal.py` | Chat-side emitter that writes `studio_signals` rows (Contract 7) and routes to item-specific executors. | `emit(...)` per the executable naming rule. Studio-level, not item-specific. |

Studio-level tool JSON (from NBB-207C, for cross-reference): `backend/app/services/tools/chat_tools/studio_signal_tool.json` → `studio/signal/tools/`.

## `studio/export/` charter note

`studio/export/` is a sanctioned studio capability group for cross-item export/render/screenshot operations. It is not a `shared/` bucket and must not collect generic helpers.

Scope: cross-item operations that every studio item can legitimately need (for example, rendering HTML to PDF, taking headless-browser screenshots of generated HTML/CSS, packaging a generated bundle for download). Any helper that is not cross-item export/render/screenshot work belongs inside its owning item directory or under a chartered `shared/` home created through a follow-up charter ticket, not under `studio/export/`.

`studio/export/` is created when the first genuine cross-item export operation lands; this file does not create placeholder files.

## Contract links (authoritative catalog: NBB-205)

Every per-item row above is tied to these contracts. Shape definitions live in `docs/contracts/README.md`; this file links, it does not redefine.

| Contract | Source | Role in the layer map |
|---|---|---|
| Contract 13 — Studio job status / progress / result | `docs/contracts/README.md` § Contract 13 | Shape contract for `<item>/schema.py` request/progress/result wire shapes; writer of record is `studio_index_service.create_job` / `update_job` (today). |
| Contract 7 — `studio_signals` / studio event shape | `docs/contracts/README.md` § Contract 7 | Shape for chat→studio routing that lands on a job; `studio/signal.py::emit(...)` is the studio-level entry point for the row writer side. |
| Contract 10 — Background-task polling response | `docs/contracts/README.md` § Contract 10 | Envelope that merges `studio_jobs` (pending + processing) into the project task feed; `job.py` status transitions must preserve the enum (`pending | processing | ready | error | cancelled`) and the human-readable `progress` string. |

Background ownership of record: `backend/app/background/tasks.py` (NBB-210). Studio items must not duplicate lifecycle state inside `<item>/job.py`; they go through `background/tasks.py`.

## Decision anchor

- Taxonomy source (locked): `backend/app/studio/TAXONOMY.md`.
- Registry source (locked): `backend/app/studio/REGISTRY.md`.
- Layer-pattern source (this file): `docs/tickets/epics/NBB-005.md#nbb-502`.
- Pilot (next ticket): `docs/tickets/epics/NBB-005.md#nbb-503`.
- Category migrations: `NBB-504` (documents), `NBB-505` (marketing), `NBB-506` (design + logo/brand support), `NBB-507` (learning + media).
- Post-migration executable-name gate: `rg 'def execute_tool\(|\.execute_tool\(' backend/app/studio` returns zero after `NBB-507`, excluding historical docs/tests.
