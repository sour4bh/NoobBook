# `studio/` canonical taxonomy (NBB-501A)

**Status:** Locked. Category and item names are fixed by the decision map in `docs/tickets/epics/NBB-005.md#nbb-501a`. This file publishes that taxonomy next to the code so `NBB-501B` can map current files to target paths without reopening the naming.

**Consumer:** `NBB-501B` builds the full studio registry on top of this taxonomy. Layer/file patterns (`<verb>.py`, `job.py`, `tool.py`, `run.py`, `schema.py`) are locked by `NBB-502`. Pilot is `NBB-503`. Category migrations are `NBB-504` through `NBB-507`.

**Not in this ticket:** moving code, creating item directories, mapping every current file, choosing prompt/tool paths beyond what `NBB-207C` already locked.

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

## Current studio service/executor concepts mapped to target items

| Current concept (under `services/studio_services/` and `services/tool_executors/`) | Canonical target item |
|---|---|
| `ad_creative_service.py`, `jobs/ad_jobs.py` | `marketing/ad/` |
| `audio_overview_service.py`, `jobs/audio_jobs.py`, `studio_audio_executor.py` | `media/audio/` |
| `blog_agent_executor.py`, `blog_tool_executor.py`, `jobs/blog_jobs.py` | `documents/blog/` |
| `business_report_agent_executor.py`, `business_report_tool_executor.py`, `jobs/business_report_jobs.py` | `documents/business_report/` |
| `component_agent_executor.py`, `component_tool_executor.py`, `jobs/component_jobs.py` | `design/component/` |
| `email_agent_executor.py`, `email_tool_executor.py`, `jobs/email_jobs.py` | `marketing/email/` |
| `flash_cards_service.py`, `jobs/flash_card_jobs.py` | `learning/flash_card/` |
| `flow_diagram_service.py`, `jobs/flow_diagram_jobs.py` | `design/flow_diagram/` |
| `infographic_service.py`, `jobs/infographic_jobs.py` | `marketing/infographic/` |
| `marketing_strategy_tool_executor.py`, `jobs/marketing_strategy_jobs.py` | `marketing/strategy/` |
| `mind_map_service.py`, `jobs/mind_map_jobs.py` | `learning/mind_map/` |
| `prd_tool_executor.py`, `jobs/prd_jobs.py` | `documents/prd/` |
| `presentation_agent_executor.py`, `presentation_tool_executor.py`, `jobs/presentation_jobs.py` | `documents/presentation/` |
| `quiz_service.py`, `jobs/quiz_jobs.py` | `learning/quiz/` |
| `social_posts_service.py`, `jobs/social_post_jobs.py` | `marketing/social_post/` |
| `video_service.py`, `video_executor.py`, `jobs/video_jobs.py` | `media/video/` |
| `website_agent_executor.py`, `website_tool_executor.py`, `jobs/website_jobs.py` | `design/website/` |
| `wireframe_tool_executor.py`, `jobs/wireframe_jobs.py` | `design/wireframe/` |

No service or executor exists for `design/logo/` today; see "Reserved slot" below. `NBB-501B` produces the exhaustive file-level registry including absent-layer (`none`) annotations; this table is a concept-level cross-reference.

## Studio-level modules (not items)

These modules live in studio but do not map to a single item. They stay as studio-level infrastructure; layer placement is owned by `NBB-502`, not this ticket.

| Current module | Role | Target surface |
|---|---|---|
| `api/studio/__init__.py` | Blueprint registrar. | Studio route blueprint (route movement deferred under `D-001`). |
| `api/studio/logo_utils.py` | Brand-asset resolution helper consumed by `ads.py`, `blogs.py`, `infographics.py`, `social_posts.py`. | Studio-level support; not an item. Placement decision (studio helper vs brand public surface) is out of scope for NBB-501A; `NBB-502`/`NBB-506` decides. |
| `services/studio_services/studio_index_service.py` | Generic CRUD for `studio_jobs`. | Studio-level job layer; `NBB-210` owns `background/` ownership, `NBB-502` maps the studio side. |
| `services/studio_services/studio_processing/` | Currently empty (`__init__.py` only). | Flagged; `NBB-502`/`NBB-501B` decide whether to retire. |
| `services/studio_services/jobs/` | Per-item `*_jobs.py` wiring (18 files). | Per-item `<item>/job.py` under `NBB-502`'s layer map; each row already attributed above. |
| `services/tool_executors/studio_signal_executor.py` | Chat-side studio-signal emitter; listed in `NBB-502` as the one studio-level executor. | `studio/signal.py::emit(...)` (NBB-502 decision, not item-owned). |

## Studio tool schemas (authoritative source: NBB-207C)

`NBB-207C` at `docs/tickets/epics/NBB-002.md#nbb-207c` is the authoritative tool-schema ownership map. Studio-owned rows are reproduced here as a cross-reference; the NBB-207C decision map wins on any conflict.

| Current tool family/file | Target owner |
|---|---|
| `services/tools/blog_agent/` | `studio/documents/blog/tools/` |
| `services/tools/business_report_agent/` | `studio/documents/business_report/tools/` |
| `services/tools/component_agent/` | `studio/design/component/tools/` |
| `services/tools/email_agent/` | `studio/marketing/email/tools/` |
| `services/tools/marketing_strategy_agent/` | `studio/marketing/strategy/tools/` |
| `services/tools/prd_agent/` | `studio/documents/prd/tools/` |
| `services/tools/presentation_agent/` | `studio/documents/presentation/tools/` |
| `services/tools/website_agent/` | `studio/design/website/tools/` |
| `services/tools/wireframe_agent/` | `studio/design/wireframe/tools/` |
| `services/tools/studio_tools/flash_cards_tool.json` | `studio/learning/flash_card/tools/` |
| `services/tools/studio_tools/flow_diagram_tool.json` | `studio/design/flow_diagram/tools/` |
| `services/tools/studio_tools/mind_map_tool.json` | `studio/learning/mind_map/tools/` |
| `services/tools/studio_tools/quiz_tool.json` | `studio/learning/quiz/tools/` |
| `services/tools/studio_tools/wireframe_tool.json` | `studio/design/wireframe/tools/` |
| `services/tools/studio_tools/write_script_section.json` | `studio/media/audio/tools/` |
| `services/tools/chat_tools/studio_signal_tool.json` | `studio/signal/tools/` |

`services/tools/studio_tools/read_source_content.json` is sources-owned (`sources/content/tools/`) per NBB-207C; it is intentionally absent from the studio list above. `NBB-207C` also notes: studio invokes `sources/content/tools/` through the sources public surface; studio does not own source reading.

## Studio prompts (deferred)

`NBB-207B` is the prompt-ownership ticket. Of the 27 prompts under `backend/data/prompts/`, `NBB-207B` moved five (`pdf_extraction_prompt.json`, `pptx_extraction_prompt.json`, `image_extraction_prompt.json`, `web_agent_prompt.json`, `deep_research_agent_prompt.json`) and deferred the rest. The studio-related prompts below remain at `backend/data/prompts/` until `NBB-207B` or a follow-on migrates them; `NBB-501B` records the target home next to each item in the studio registry.

| Current prompt | Target item (for NBB-501B registry, not moved here) |
|---|---|
| `ad_creative_prompt.json` | `studio/marketing/ad/prompts/` |
| `audio_script_prompt.json` | `studio/media/audio/prompts/` |
| `blog_agent_prompt.json` | `studio/documents/blog/prompts/` |
| `business_report_agent_prompt.json` | `studio/documents/business_report/prompts/` |
| `component_agent_prompt.json` | `studio/design/component/prompts/` |
| `email_agent_prompt.json` | `studio/marketing/email/prompts/` |
| `flash_cards_prompt.json` | `studio/learning/flash_card/prompts/` |
| `flow_diagram_prompt.json` | `studio/design/flow_diagram/prompts/` |
| `infographic_prompt.json` | `studio/marketing/infographic/prompts/` |
| `marketing_strategy_agent_prompt.json` | `studio/marketing/strategy/prompts/` |
| `mind_map_prompt.json` | `studio/learning/mind_map/prompts/` |
| `prd_agent_prompt.json` | `studio/documents/prd/prompts/` |
| `presentation_agent_prompt.json` | `studio/documents/presentation/prompts/` |
| `quiz_prompt.json` | `studio/learning/quiz/prompts/` |
| `social_posts_prompt.json` | `studio/marketing/social_post/prompts/` |
| `video_prompt.json` | `studio/media/video/prompts/` |
| `website_agent_prompt.json` | `studio/design/website/prompts/` |
| `wireframe_agent_prompt.json` | `studio/design/wireframe/prompts/` |
| `wireframe_prompt.json` | `studio/design/wireframe/prompts/` |

No studio prompt asset is moved by this ticket.

## Reserved slot: `design/logo/`

`design/logo/` is reserved for logo generation. No route, service, job, tool executor, tool schema, or prompt exists for it today. `logo_utils.py` resolves brand-asset bytes (logos/icons uploaded via the brand domain) for Gemini multimodal generation in other items; it is not logo generation and is not item-owned. Brand asset/config storage remains brand-owned (migrated in `NBB-209D`). When logo generation lands, it lands at `studio/design/logo/`.

## Decision anchor

Any future studio item must claim exactly one category/item path from this file or extend it through a new NBB-501A-style ticket. Do not invent categories or merge items.

- Decision source (locked): `docs/tickets/epics/NBB-005.md#nbb-501a`.
- Tool-schema paths (locked): `docs/tickets/epics/NBB-002.md#nbb-207c`.
- Registry owner (next ticket): `docs/tickets/epics/NBB-005.md#nbb-501b`.
- Layer/file patterns (next ticket): `docs/tickets/epics/NBB-005.md#nbb-502`.
