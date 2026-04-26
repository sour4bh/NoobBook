# `studio/` canonical taxonomy (NBB-501A)

**Status:** Locked. Category and item names are fixed by the decision map in `docs/tickets/epics/NBB-005.md#nbb-501a`. This file publishes that taxonomy next to the code so `NBB-501B` can map current files to target paths without reopening the naming.

**Consumer:** `NBB-501B` builds the full studio registry on top of this taxonomy. Layer/file patterns (`<verb>.py`, `job.py`, `tool.py`, `run.py`, `schema.py`) are locked by `NBB-502`. Pilot is `NBB-503`. Category migrations are `NBB-504` through `NBB-507`.

**Post-sprint note:** This taxonomy still owns names only, but the cross-reference tables below now point at the migrated `backend/app/studio/**` item homes rather than the pre-sprint mechanism buckets.

## Categories and items

Five categories. Nineteen items. Category directories are plural domain groups; item directories are singular local concepts. Do not invent new categories ("multimedia", "creative", "content" are not valid). Do not merge items.

| Category | Item path | What it covers |
|---|---|---|
| Documents | `documents/blog/` | Long-form blog posts. |
| Documents | `documents/business_report/` | Business/analytical reports. |
| Documents | `documents/prd/` | Product requirements documents. |
| Documents | `documents/presentation/` | Slide decks. |
| Marketing | `marketing/ad/` | Ad creatives (image-first). |
| Marketing | `marketing/email/` | Email templates. |
| Marketing | `marketing/infographic/` | Single-image infographics. |
| Marketing | `marketing/strategy/` | Marketing strategy documents. |
| Marketing | `marketing/social_post/` | Platform-specific social posts. |
| Design | `design/component/` | Reusable UI components. |
| Design | `design/flow_diagram/` | Mermaid flow/relationship diagrams. |
| Design | `design/logo/` | Logo generation (reserved slot; see below). |
| Design | `design/website/` | Multi-page HTML/CSS/JS sites. |
| Design | `design/wireframe/` | UI/UX wireframes. |
| Learning | `learning/flash_card/` | Flash-card Q&A sets. |
| Learning | `learning/mind_map/` | Hierarchical concept maps. |
| Learning | `learning/quiz/` | Multiple-choice quizzes. |
| Media | `media/audio/` | Audio overviews (TTS). |
| Media | `media/video/` | Video generation. |

Audio and video are separate item slices under `media/`; there is no combined media item.

## Current studio routes mapped to target items

Inventoried against `backend/app/api/studio/*.py`. Every route file maps to exactly one locked item. `__init__.py` is the blueprint registrar; `logo_utils.py` is studio-level brand-asset resolution support (see "Studio-level modules" below) and is not a route file.

| Current route file | Canonical target item |
|---|---|
| `api/studio/ads.py` | `marketing/ad/` |
| `api/studio/audio.py` | `media/audio/` |
| `api/studio/blogs.py` | `documents/blog/` |
| `api/studio/business_reports.py` | `documents/business_report/` |
| `api/studio/components.py` | `design/component/` |
| `api/studio/emails.py` | `marketing/email/` |
| `api/studio/flash_cards.py` | `learning/flash_card/` |
| `api/studio/flow_diagrams.py` | `design/flow_diagram/` |
| `api/studio/infographics.py` | `marketing/infographic/` |
| `api/studio/marketing_strategies.py` | `marketing/strategy/` |
| `api/studio/mind_maps.py` | `learning/mind_map/` |
| `api/studio/prds.py` | `documents/prd/` |
| `api/studio/presentations.py` | `documents/presentation/` |
| `api/studio/quizzes.py` | `learning/quiz/` |
| `api/studio/social_posts.py` | `marketing/social_post/` |
| `api/studio/videos.py` | `media/video/` |
| `api/studio/websites.py` | `design/website/` |
| `api/studio/wireframes.py` | `design/wireframe/` |

Route *file movement* stays deferred under `D-001`; this table fixes target *item ownership* only. `NBB-501B` maps each route file's services, jobs, tool executors, prompts, and tool schemas to the same target item.

## Current studio item modules mapped to target items

| Current item modules | Canonical target item |
|---|---|
| `backend/app/studio/marketing/ad/{create,job}.py` | `marketing/ad/` |
| `backend/app/studio/media/audio/{generate,job,tool}.py` | `media/audio/` |
| `backend/app/studio/documents/blog/{write,tool,run,job}.py` | `documents/blog/` |
| `backend/app/studio/documents/business_report/{write,tool,run,job}.py` | `documents/business_report/` |
| `backend/app/studio/design/component/{build,tool,run,job}.py` | `design/component/` |
| `backend/app/studio/marketing/email/{write,tool,run,job}.py` | `marketing/email/` |
| `backend/app/studio/learning/flash_card/{create,job}.py` | `learning/flash_card/` |
| `backend/app/studio/design/flow_diagram/{create,job}.py` | `design/flow_diagram/` |
| `backend/app/studio/marketing/infographic/{create,job}.py` | `marketing/infographic/` |
| `backend/app/studio/marketing/strategy/{plan,tool,job}.py` | `marketing/strategy/` |
| `backend/app/studio/learning/mind_map/{create,job}.py` | `learning/mind_map/` |
| `backend/app/studio/documents/prd/{write,tool,job}.py` | `documents/prd/` |
| `backend/app/studio/documents/presentation/{compose,tool,run,job}.py` | `documents/presentation/` |
| `backend/app/studio/learning/quiz/{create,job}.py` | `learning/quiz/` |
| `backend/app/studio/marketing/social_post/{write,job}.py` | `marketing/social_post/` |
| `backend/app/studio/media/video/{generate,job,tool}.py` | `media/video/` |
| `backend/app/studio/design/website/{build,tool,run,job}.py` | `design/website/` |
| `backend/app/studio/design/wireframe/{draw,tool,job}.py` | `design/wireframe/` |

No service or executor exists for `design/logo/` today; see "Reserved slot" below. `NBB-501B` produces the exhaustive file-level registry including absent-layer (`none`) annotations; this table is a concept-level cross-reference.

## Studio-level modules (not items)

These modules live in studio but do not map to a single item. They stay as studio-level infrastructure; layer placement is owned by `NBB-502`, not this ticket.

| Current module | Role | Target surface |
|---|---|---|
| `api/studio/__init__.py` | Blueprint registrar. | Studio route blueprint (route movement deferred under `D-001`). |
| `api/studio/logo_utils.py` | Brand-asset resolution helper consumed by `ads.py`, `blogs.py`, `infographics.py`, `social_posts.py`. | Studio-level support; not an item. Placement decision (studio helper vs brand public surface) is out of scope for NBB-501A; `NBB-502`/`NBB-506` decides. |
| `services/studio_services/studio_index_service.py` | Generic CRUD for `studio_jobs`. | Studio-level job index; the package is doc-only and consumers import the submodule explicitly. |
| Removed `studio_processing/` package | Empty package deleted during cleanup. | No runtime surface. |
| Per-item `job.py` modules | Per-item background job wiring in the item directories listed above. | No forwarding jobs package remains. |
| `studio/signal.py` | Chat-side studio-signal emitter; listed in `NBB-502` as the one studio-level executor. | `emit(...)` (NBB-502 decision, not item-owned). |

## Studio tool schemas (authoritative source: NBB-207C)

`NBB-207C` at `docs/tickets/epics/NBB-002.md#nbb-207c` is the authoritative tool-schema ownership map. Studio-owned rows are reproduced here as a cross-reference; the NBB-207C decision map wins on any conflict.

| Current tool family/file | Owner |
|---|---|
| `studio/documents/blog/tools/` | `studio/documents/blog/tools/` |
| `studio/documents/business_report/tools/` | `studio/documents/business_report/tools/` |
| `studio/design/component/tools/` | `studio/design/component/tools/` |
| `studio/marketing/email/tools/` | `studio/marketing/email/tools/` |
| `studio/marketing/strategy/tools/` | `studio/marketing/strategy/tools/` |
| `studio/documents/prd/tools/` | `studio/documents/prd/tools/` |
| `studio/documents/presentation/tools/` | `studio/documents/presentation/tools/` |
| `studio/design/website/tools/` | `studio/design/website/tools/` |
| `studio/design/wireframe/tools/` | `studio/design/wireframe/tools/` |
| `studio/learning/flash_card/tools/` | `studio/learning/flash_card/tools/` |
| `studio/design/flow_diagram/tools/` | `studio/design/flow_diagram/tools/` |
| `studio/learning/mind_map/tools/` | `studio/learning/mind_map/tools/` |
| `studio/learning/quiz/tools/` | `studio/learning/quiz/tools/` |
| `studio/media/audio/tools/` | `studio/media/audio/tools/` |
| `services/tools/chat_tools/studio_signal_tool.json` | `studio/signal/tools/` |

`services/tools/studio_tools/read_source_content.json` is sources-owned (`sources/content/tools/`) per NBB-207C; it is intentionally absent from the studio list above. `NBB-207C` also notes: studio invokes `sources/content/tools/` through the sources public surface; studio does not own source reading.

## Studio prompts

Studio-related prompts now live under item-owned `prompts/` directories.

| Current prompt | Owner |
|---|---|
| `studio/marketing/ad/prompts/ad_creative_prompt.json` | `studio/marketing/ad/prompts/` |
| `studio/media/audio/prompts/audio_script_prompt.json` | `studio/media/audio/prompts/` |
| `studio/documents/blog/prompts/blog_agent_prompt.json` | `studio/documents/blog/prompts/` |
| `studio/documents/business_report/prompts/business_report_agent_prompt.json` | `studio/documents/business_report/prompts/` |
| `studio/design/component/prompts/component_agent_prompt.json` | `studio/design/component/prompts/` |
| `studio/marketing/email/prompts/email_agent_prompt.json` | `studio/marketing/email/prompts/` |
| `studio/learning/flash_card/prompts/flash_cards_prompt.json` | `studio/learning/flash_card/prompts/` |
| `studio/design/flow_diagram/prompts/flow_diagram_prompt.json` | `studio/design/flow_diagram/prompts/` |
| `studio/marketing/infographic/prompts/infographic_prompt.json` | `studio/marketing/infographic/prompts/` |
| `studio/marketing/strategy/prompts/marketing_strategy_agent_prompt.json` | `studio/marketing/strategy/prompts/` |
| `studio/learning/mind_map/prompts/mind_map_prompt.json` | `studio/learning/mind_map/prompts/` |
| `studio/documents/prd/prompts/prd_agent_prompt.json` | `studio/documents/prd/prompts/` |
| `studio/documents/presentation/prompts/presentation_agent_prompt.json` | `studio/documents/presentation/prompts/` |
| `studio/learning/quiz/prompts/quiz_prompt.json` | `studio/learning/quiz/prompts/` |
| `studio/marketing/social_post/prompts/social_posts_prompt.json` | `studio/marketing/social_post/prompts/` |
| `studio/media/video/prompts/video_prompt.json` | `studio/media/video/prompts/` |
| `studio/design/website/prompts/website_agent_prompt.json` | `studio/design/website/prompts/` |
| `studio/design/wireframe/prompts/wireframe_agent_prompt.json` | `studio/design/wireframe/prompts/` |
| `studio/design/wireframe/prompts/wireframe_prompt.json` | `studio/design/wireframe/prompts/` |

## Reserved slot: `design/logo/`

`design/logo/` is reserved for logo generation. No route, service, job, tool executor, tool schema, or prompt exists for it today. `logo_utils.py` resolves brand-asset bytes (logos/icons uploaded via the brand domain) for Gemini multimodal generation in other items; it is not logo generation and is not item-owned. Brand asset/config storage remains brand-owned (migrated in `NBB-209D`). When logo generation lands, it lands at `studio/design/logo/`.

## Decision anchor

Any future studio item must claim exactly one category/item path from this file or extend it through a new NBB-501A-style ticket. Do not invent categories or merge items.

- Decision source (locked): `docs/tickets/epics/NBB-005.md#nbb-501a`.
- Tool-schema paths (locked): `docs/tickets/epics/NBB-002.md#nbb-207c`.
- Registry owner (next ticket): `docs/tickets/epics/NBB-005.md#nbb-501b`.
- Layer/file patterns (next ticket): `docs/tickets/epics/NBB-005.md#nbb-502`.
