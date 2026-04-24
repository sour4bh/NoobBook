# `studio/` final item registry (NBB-501B)

**Status:** Locked for `NBB-502` layer mapping, `NBB-503` pilot, and `NBB-504`–`NBB-507` migrations. Item and category names come verbatim from `TAXONOMY.md` (NBB-501A); do not invent new names.

**Authority:** `TAXONOMY.md` locks categories and items. This file records, for every one of the 19 items, the current route/service/job/tool-executor/prompt/tool-JSON/tests, the target path under `backend/app/studio/<category>/<item>/`, and which upstream ownership tickets govern each moving part. This file names current homes; it does not move code, prompts, or tool JSON.

## Upstream ownership linkage

All rows below follow one linkage table. Per-row entries use the short label on the left; full definition lives at the referenced source.

| Label | Meaning | Source |
|---|---|---|
| `Contract 13` | Studio job status / progress / result | `docs/contracts/README.md` § Contract 13 (NBB-205) |
| `Contract 7` | `studio_signals` / studio event shape | `docs/contracts/README.md` § Contract 7 (NBB-205) |
| `Contract 10` | Background-task polling response | `docs/contracts/README.md` § Contract 10 (NBB-205) |
| `background/tasks.py` | Canonical background surface | `backend/app/background/tasks.py` (NBB-210) |
| `studio_jobs` (table) | Studio-owned job index | `studio_index_service.py` + `backend/supabase/migrations/00009_studio_jobs.sql` (NBB-204) |
| Provider: Claude | Anthropic Messages API | `providers/CHARTER.md` (NBB-206) |
| Provider: Gemini Imagen | Google Imagen image generation | `providers/CHARTER.md` (NBB-206) |
| Provider: Google Veo | Google Veo video generation | `providers/CHARTER.md` (NBB-206) |
| Provider: ElevenLabs TTS | ElevenLabs text-to-speech | `providers/CHARTER.md` (NBB-206) |
| Prompt ownership | Prompt JSON decision map | `docs/tickets/epics/NBB-002.md#nbb-207b` |
| Tool JSON ownership | Tool JSON decision map | `docs/tickets/epics/NBB-002.md#nbb-207c` |

**Prompt/tool JSON status note (NBB-207B + NBB-207C):** No studio prompt has moved yet; all 19 studio-related prompts remain under `backend/data/prompts/`. No studio tool JSON has moved yet; all studio tool families remain under `backend/app/services/tools/`. Each row below records the current path and the owning-domain path from the NBB-207B/NBB-207C decision maps. The physical moves land in `NBB-504`–`NBB-507`.

**Tests status note:** No item-specific studio tests exist at base commit. The studio blueprint is covered generically by `backend/tests/api/test_blueprint_registration.py` and `backend/tests/api/test_blueprint_smoke.py` (a single `GET /api/v1/studio/gemini/status` route smoke). Item rows record `none` for item-specific tests and rely on the blueprint-level coverage. The one dedicated executor test is `backend/tests/test_website_tool_executor.py`, which is attached to the `design/website/` row only.

**Route file movement note (D-001):** Every row's "route file" stays under `backend/app/api/studio/` during this migration; `D-001` defers route movement out of `backend/app/api/`. The registry records route files as current ownership anchors only.

---

## Documents

<a id="documents-blog"></a>
### `documents/blog/` — Long-form blog posts

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/blogs.py` | stays under `api/studio/` (D-001); public surface target `studio/documents/blog/` |
| Service (domain) | `backend/app/services/ai_agents/blog_agent_service.py` | `backend/app/studio/documents/blog/` (NBB-504) |
| Tool executor | `backend/app/services/tool_executors/blog_tool_executor.py` | `backend/app/studio/documents/blog/` (NBB-504) |
| Agent executor | `backend/app/services/tool_executors/blog_agent_executor.py` | `backend/app/studio/documents/blog/` (NBB-504) |
| Job wiring | `backend/app/services/studio_services/jobs/blog_jobs.py` | `backend/app/studio/documents/blog/` (NBB-504) |
| Prompt JSON | `backend/data/prompts/blog_agent_prompt.json` | owning domain: `studio/documents/blog/prompts/` (NBB-207B deferred; lands in NBB-504) |
| Tool JSON | `backend/app/services/tools/blog_agent/` (`generate_blog_image.json`, `plan_blog_post.json`, `write_blog_post.json`) | owning domain: `studio/documents/blog/tools/` (NBB-207C deferred; lands in NBB-504) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (planning + writing); Gemini Imagen (hero/section images) | NBB-206 |

<a id="documents-business_report"></a>
### `documents/business_report/` — Business/analytical reports

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/business_reports.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/business_report_agent_service.py` | `backend/app/studio/documents/business_report/` (NBB-504) |
| Tool executor | `backend/app/services/tool_executors/business_report_tool_executor.py` | `backend/app/studio/documents/business_report/` (NBB-504) |
| Agent executor | `backend/app/services/tool_executors/business_report_agent_executor.py` | `backend/app/studio/documents/business_report/` (NBB-504) |
| Job wiring | `backend/app/services/studio_services/jobs/business_report_jobs.py` | `backend/app/studio/documents/business_report/` (NBB-504) |
| Prompt JSON | `backend/data/prompts/business_report_agent_prompt.json` | owning domain: `studio/documents/business_report/prompts/` (NBB-207B deferred; NBB-504) |
| Tool JSON | `backend/app/services/tools/business_report_agent/` (`analyze_csv_data.json`, `plan_business_report.json`, `search_source_content.json`, `write_business_report.json`) | owning domain: `studio/documents/business_report/tools/` (NBB-207C deferred; NBB-504) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="documents-prd"></a>
### `documents/prd/` — Product requirements documents

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/prds.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/prd_agent_service.py` | `backend/app/studio/documents/prd/` (NBB-504) |
| Tool executor | `backend/app/services/tool_executors/prd_tool_executor.py` | `backend/app/studio/documents/prd/` (NBB-504) |
| Agent executor | none | prd uses `is_last_section` termination in tool executor; no separate agent executor |
| Job wiring | `backend/app/services/studio_services/jobs/prd_jobs.py` | `backend/app/studio/documents/prd/` (NBB-504) |
| Prompt JSON | `backend/data/prompts/prd_agent_prompt.json` | owning domain: `studio/documents/prd/prompts/` (NBB-207B deferred; NBB-504) |
| Tool JSON | `backend/app/services/tools/prd_agent/` (`plan_prd.json`, `write_prd_section.json`) | owning domain: `studio/documents/prd/tools/` (NBB-207C deferred; NBB-504) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="documents-presentation"></a>
### `documents/presentation/` — Slide decks

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/presentations.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/presentation_agent_service.py` | `backend/app/studio/documents/presentation/` (NBB-504) |
| Tool executor | `backend/app/services/tool_executors/presentation_tool_executor.py` | `backend/app/studio/documents/presentation/` (NBB-504) |
| Agent executor | `backend/app/services/tool_executors/presentation_agent_executor.py` | `backend/app/studio/documents/presentation/` (NBB-504) |
| Job wiring | `backend/app/services/studio_services/jobs/presentation_jobs.py` | `backend/app/studio/documents/presentation/` (NBB-504) |
| Prompt JSON | `backend/data/prompts/presentation_agent_prompt.json` | owning domain: `studio/documents/presentation/prompts/` (NBB-207B deferred; NBB-504) |
| Tool JSON | `backend/app/services/tools/presentation_agent/` (`create_base_styles.json`, `create_slide.json`, `finalize_presentation.json`, `plan_presentation.json`) | owning domain: `studio/documents/presentation/tools/` (NBB-207C deferred; NBB-504) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

---

## Marketing

<a id="marketing-ad"></a>
### `marketing/ad/` — Ad creatives (image-first)

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/ads.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/ad_creative_service.py` | `backend/app/studio/marketing/ad/` (NBB-505) |
| Tool executor | none | image-first service; no agent tool loop |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/ad_jobs.py` | `backend/app/studio/marketing/ad/` (NBB-505) |
| Prompt JSON | `backend/data/prompts/ad_creative_prompt.json` | owning domain: `studio/marketing/ad/prompts/` (NBB-207B deferred; NBB-505). Reconciliation: NBB-207B records category-level `studio/marketing/prompts/`; REGISTRY refines to item-level per TAXONOMY precedent; NBB-505 lands final path. |
| Tool JSON | none | ad creative has no Claude tool schema |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (prompt planning); Gemini Imagen (image generation) | NBB-206 |

<a id="marketing-email"></a>
### `marketing/email/` — Email templates

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/emails.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/email_agent_service.py` | `backend/app/studio/marketing/email/` (NBB-505) |
| Tool executor | `backend/app/services/tool_executors/email_tool_executor.py` | `backend/app/studio/marketing/email/` (NBB-505) |
| Agent executor | `backend/app/services/tool_executors/email_agent_executor.py` | `backend/app/studio/marketing/email/` (NBB-505) |
| Job wiring | `backend/app/services/studio_services/jobs/email_jobs.py` | `backend/app/studio/marketing/email/` (NBB-505) |
| Prompt JSON | `backend/data/prompts/email_agent_prompt.json` | owning domain: `studio/marketing/email/prompts/` (NBB-207B deferred; NBB-505) |
| Tool JSON | `backend/app/services/tools/email_agent/` (`generate_email_image.json`, `plan_email_template.json`, `write_email_code.json`) | owning domain: `studio/marketing/email/tools/` (NBB-207C deferred; NBB-505) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (planning + writing); Gemini Imagen (email images) | NBB-206 |

<a id="marketing-infographic"></a>
### `marketing/infographic/` — Single-image infographics

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/infographics.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/infographic_service.py` | `backend/app/studio/marketing/infographic/` (NBB-505) |
| Tool executor | none | image-first service; no agent tool loop |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/infographic_jobs.py` | `backend/app/studio/marketing/infographic/` (NBB-505) |
| Prompt JSON | `backend/data/prompts/infographic_prompt.json` | owning domain: `studio/marketing/infographic/prompts/` (NBB-207B deferred; NBB-505). Reconciliation (category drift): NBB-207B assigns infographic to `studio/design/prompts/`; TAXONOMY.md (NBB-501A) locks infographic under `studio/marketing/`; REGISTRY follows TAXONOMY; NBB-505 and a follow-up NBB-207B sweep must reconcile before final placement. |
| Tool JSON | none | infographic has no Claude tool schema |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (prompt planning); Gemini Imagen (image generation) | NBB-206 |

<a id="marketing-strategy"></a>
### `marketing/strategy/` — Marketing strategy documents

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/marketing_strategies.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/marketing_strategy_agent_service.py` | `backend/app/studio/marketing/strategy/` (NBB-505) |
| Tool executor | `backend/app/services/tool_executors/marketing_strategy_tool_executor.py` | `backend/app/studio/marketing/strategy/` (NBB-505) |
| Agent executor | none | marketing_strategy has no separate agent executor |
| Job wiring | `backend/app/services/studio_services/jobs/marketing_strategy_jobs.py` | `backend/app/studio/marketing/strategy/` (NBB-505) |
| Prompt JSON | `backend/data/prompts/marketing_strategy_agent_prompt.json` | owning domain: `studio/marketing/strategy/prompts/` (NBB-207B deferred; NBB-505) |
| Tool JSON | `backend/app/services/tools/marketing_strategy_agent/` (`plan_marketing_strategy.json`, `write_marketing_section.json`) | owning domain: `studio/marketing/strategy/tools/` (NBB-207C deferred; NBB-505) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="marketing-social_post"></a>
### `marketing/social_post/` — Platform-specific social posts

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/social_posts.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/social_posts_service.py` | `backend/app/studio/marketing/social_post/` (NBB-505) |
| Tool executor | none | image-first + templated text; no agent tool loop |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/social_post_jobs.py` | `backend/app/studio/marketing/social_post/` (NBB-505) |
| Prompt JSON | `backend/data/prompts/social_posts_prompt.json` | owning domain: `studio/marketing/social_post/prompts/` (NBB-207B deferred; NBB-505). Reconciliation: NBB-207B records category-level `studio/marketing/prompts/`; REGISTRY refines to item-level per TAXONOMY precedent; NBB-505 lands final path. |
| Tool JSON | none | social_post has no Claude tool schema |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (text); Gemini Imagen (post images) | NBB-206 |

---

## Design

<a id="design-component"></a>
### `design/component/` — Reusable UI components

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/components.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/component_agent_service.py` | `backend/app/studio/design/component/` (NBB-506) |
| Tool executor | `backend/app/services/tool_executors/component_tool_executor.py` | `backend/app/studio/design/component/` (NBB-506) |
| Agent executor | `backend/app/services/tool_executors/component_agent_executor.py` | `backend/app/studio/design/component/` (NBB-506) |
| Job wiring | `backend/app/services/studio_services/jobs/component_jobs.py` | `backend/app/studio/design/component/` (NBB-506) |
| Prompt JSON | `backend/data/prompts/component_agent_prompt.json` | owning domain: `studio/design/component/prompts/` (NBB-207B deferred; NBB-506) |
| Tool JSON | `backend/app/services/tools/component_agent/` (`plan_components.json`, `write_component_code.json`) | owning domain: `studio/design/component/tools/` (NBB-207C deferred; NBB-506) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="design-flow_diagram"></a>
### `design/flow_diagram/` — Mermaid flow/relationship diagrams

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/flow_diagrams.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/flow_diagram_service.py` | `backend/app/studio/design/flow_diagram/` (NBB-506) |
| Tool executor | none | single Claude call with `flow_diagram_tool.json`; no tool executor module |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/flow_diagram_jobs.py` | `backend/app/studio/design/flow_diagram/` (NBB-506) |
| Prompt JSON | `backend/data/prompts/flow_diagram_prompt.json` | owning domain: `studio/design/flow_diagram/prompts/` (NBB-207B deferred; NBB-506) |
| Tool JSON | `backend/app/services/tools/studio_tools/flow_diagram_tool.json` | owning domain: `studio/design/flow_diagram/tools/` (NBB-207C deferred; NBB-506) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="design-logo"></a>
### `design/logo/` — Logo generation (reserved slot)

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | none | reserved; `NBB-506` decides whether logo generation lands as a new route or as part of brand domain |
| Service (domain) | none | reserved |
| Tool executor | none | reserved |
| Agent executor | none | reserved |
| Job wiring | none | reserved |
| Prompt JSON | none | reserved |
| Tool JSON | none | reserved |
| Tests | none | n/a |
| Background | none | n/a |
| Providers | none | n/a |

`api/studio/logo_utils.py` is a studio-level brand-asset resolver consumed by `ads.py`, `blogs.py`, `infographics.py`, and `social_posts.py`. It is **not** logo generation; see "Studio-level modules (not items)" at the bottom of this file. Brand asset/config storage remains brand-owned (moved in `NBB-209D`).

<a id="design-website"></a>
### `design/website/` — Multi-page HTML/CSS/JS sites

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/websites.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/website_agent_service.py` | `backend/app/studio/design/website/` (NBB-506) |
| Tool executor | `backend/app/services/tool_executors/website_tool_executor.py` | `backend/app/studio/design/website/` (NBB-506) |
| Agent executor | `backend/app/services/tool_executors/website_agent_executor.py` | `backend/app/studio/design/website/` (NBB-506) |
| Job wiring | `backend/app/services/studio_services/jobs/website_jobs.py` | `backend/app/studio/design/website/` (NBB-506) |
| Prompt JSON | `backend/data/prompts/website_agent_prompt.json` | owning domain: `studio/design/website/prompts/` (NBB-207B deferred; NBB-506) |
| Tool JSON | `backend/app/services/tools/website_agent/` (`create_file.json`, `finalize_website.json`, `generate_website_image.json`, `insert_code.json`, `plan_website.json`, `read_file.json`, `update_file_lines.json`) | owning domain: `studio/design/website/tools/` (NBB-207C deferred; NBB-506) |
| Tests | `backend/tests/test_website_tool_executor.py` | only item-specific studio test at base commit |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (planning + writing); Gemini Imagen (website images) | NBB-206 |

<a id="design-wireframe"></a>
### `design/wireframe/` — UI/UX wireframes

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/wireframes.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/ai_agents/wireframe_agent_service.py` | `backend/app/studio/design/wireframe/` (NBB-506) |
| Tool executor | `backend/app/services/tool_executors/wireframe_tool_executor.py` | `backend/app/studio/design/wireframe/` (NBB-506) |
| Agent executor | none | wireframe has no separate agent executor |
| Job wiring | `backend/app/services/studio_services/jobs/wireframe_jobs.py` | `backend/app/studio/design/wireframe/` (NBB-506) |
| Prompt JSON | `backend/data/prompts/wireframe_agent_prompt.json`, `backend/data/prompts/wireframe_prompt.json` | both map to `studio/design/wireframe/prompts/` (NBB-207B deferred; NBB-506). Two prompts exist: one for the multi-section agent flow and one for the single-shot wireframe path. |
| Tool JSON | `backend/app/services/tools/wireframe_agent/` (`add_wireframe_section.json`, `finalize_wireframe.json`, `plan_wireframe.json`) plus `backend/app/services/tools/studio_tools/wireframe_tool.json` | all map to `studio/design/wireframe/tools/` (NBB-207C deferred; NBB-506) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

---

## Learning

<a id="learning-flash_card"></a>
### `learning/flash_card/` — Flash-card Q&A sets

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/flash_cards.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/flash_cards_service.py` | `backend/app/studio/learning/flash_card/` (NBB-507) |
| Tool executor | none | single Claude call with `flash_cards_tool.json`; no tool executor module |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/flash_card_jobs.py` | `backend/app/studio/learning/flash_card/` (NBB-507) |
| Prompt JSON | `backend/data/prompts/flash_cards_prompt.json` | owning domain: `studio/learning/flash_card/prompts/` (NBB-207B deferred; NBB-507) |
| Tool JSON | `backend/app/services/tools/studio_tools/flash_cards_tool.json` | owning domain: `studio/learning/flash_card/tools/` (NBB-207C deferred; NBB-507) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="learning-mind_map"></a>
### `learning/mind_map/` — Hierarchical concept maps

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/mind_maps.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/mind_map_service.py` | `backend/app/studio/learning/mind_map/` (NBB-507) |
| Tool executor | none | single Claude call with `mind_map_tool.json`; no tool executor module |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/mind_map_jobs.py` | `backend/app/studio/learning/mind_map/` (NBB-507) |
| Prompt JSON | `backend/data/prompts/mind_map_prompt.json` | owning domain: `studio/learning/mind_map/prompts/` (NBB-207B deferred; NBB-507) |
| Tool JSON | `backend/app/services/tools/studio_tools/mind_map_tool.json` | owning domain: `studio/learning/mind_map/tools/` (NBB-207C deferred; NBB-507) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

<a id="learning-quiz"></a>
### `learning/quiz/` — Multiple-choice quizzes

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/quizzes.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/quiz_service.py` | `backend/app/studio/learning/quiz/` (NBB-507) |
| Tool executor | none | single Claude call with `quiz_tool.json`; no tool executor module |
| Agent executor | none | n/a |
| Job wiring | `backend/app/services/studio_services/jobs/quiz_jobs.py` | `backend/app/studio/learning/quiz/` (NBB-507) |
| Prompt JSON | `backend/data/prompts/quiz_prompt.json` | owning domain: `studio/learning/quiz/prompts/` (NBB-207B deferred; NBB-507) |
| Tool JSON | `backend/app/services/tools/studio_tools/quiz_tool.json` | owning domain: `studio/learning/quiz/tools/` (NBB-207C deferred; NBB-507) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude | NBB-206 |

---

## Media

<a id="media-audio"></a>
### `media/audio/` — Audio overviews (TTS)

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/audio.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/audio_overview_service.py` | `backend/app/studio/media/audio/` (NBB-507) |
| Tool executor | `backend/app/services/tool_executors/studio_audio_executor.py` | `backend/app/studio/media/audio/` (NBB-507). Handles `read_source_content` (sources-owned tool invoked via sources public surface) + `write_script_section` (studio-owned). |
| Agent executor | none | audio uses the tool-executor agentic loop directly |
| Job wiring | `backend/app/services/studio_services/jobs/audio_jobs.py` | `backend/app/studio/media/audio/` (NBB-507) |
| Prompt JSON | `backend/data/prompts/audio_script_prompt.json` | owning domain: `studio/media/audio/prompts/` (NBB-207B deferred; NBB-507) |
| Tool JSON | `backend/app/services/tools/studio_tools/write_script_section.json` | owning domain: `studio/media/audio/tools/` (NBB-207C deferred; NBB-507). `backend/app/services/tools/studio_tools/read_source_content.json` is **sources-owned** (`sources/content/tools/`) per NBB-207C and is not part of this item's tool inventory. |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10 |
| Providers | Claude (script writing); ElevenLabs TTS (audio synthesis) | NBB-206 |

<a id="media-video"></a>
### `media/video/` — Video generation

| Layer | Current | Target / Notes |
|---|---|---|
| Route file | `backend/app/api/studio/videos.py` | stays under `api/studio/` (D-001) |
| Service (domain) | `backend/app/services/studio_services/video_service.py` | `backend/app/studio/media/video/` (NBB-507) |
| Tool executor | `backend/app/services/tool_executors/video_executor.py` | `backend/app/studio/media/video/` (NBB-507). Studio-signal router: creates a job and launches background generation from a chat studio_signal. |
| Agent executor | none | video service is a single-call generator, not an agentic loop |
| Job wiring | `backend/app/services/studio_services/jobs/video_jobs.py` | `backend/app/studio/media/video/` (NBB-507) |
| Prompt JSON | `backend/data/prompts/video_prompt.json` | owning domain: `studio/media/video/prompts/` (NBB-207B deferred; NBB-507) |
| Tool JSON | none | video has no item-owned Claude tool schema; invoked via studio_signal (Contract 7) |
| Tests | none | blueprint-level smoke only |
| Background | `studio_jobs` via `studio_index_service.py` + `background/tasks.py` | Contract 13; Contract 10; Contract 7 (studio_signal entrypoint) |
| Providers | Claude (prompt planning); Google Veo (video generation) | NBB-206 |

---

## Studio-level modules (not items)

These modules live in the studio domain but are not item-owned. They stay as studio-level infrastructure; file-level layer placement is owned by `NBB-502`, not this registry.

| Current module | Role | Target surface |
|---|---|---|
| `backend/app/api/studio/__init__.py` | Studio blueprint registrar and project-access guard. | Studio blueprint; route file movement deferred under `D-001`. |
| `backend/app/api/studio/logo_utils.py` | Brand-asset resolution helper consumed by `ads.py`, `blogs.py`, `infographics.py`, `social_posts.py`. | Studio-level support. Placement decision (studio helper vs brand public surface) lands in `NBB-502`/`NBB-506`. |
| `backend/app/services/studio_services/studio_index_service.py` | Generic CRUD for the `studio_jobs` table (per-item create/update/get/list/delete wrappers). | Studio-level job layer. `NBB-210` owns `background/tasks.py`; `NBB-502` maps the studio-side surface. |
| `backend/app/services/studio_services/studio_processing/` | Currently empty (only `__init__.py`). | `NBB-502`/`NBB-503` decide whether to retire the package. |
| `backend/app/services/studio_services/jobs/` | Per-item `*_jobs.py` wiring (18 files, listed per item above). | Per-item `<item>/job.py` under `NBB-502`'s layer map; each file is attributed to its item row above. |
| `backend/app/services/tool_executors/studio_signal_executor.py` | Chat-side emitter that writes `studio_signals` rows and routes to item-specific executors (`video_executor.py` today, others as they land). | `studio/signal.py::emit(...)` (NBB-502 decision); studio-level, not item-owned. |

Studio-level tool JSON (from NBB-207C): `backend/app/services/tools/chat_tools/studio_signal_tool.json` → `studio/signal/tools/` (studio-level, not item-owned).

## Decision anchor

Any future studio item must claim exactly one category/item path from `TAXONOMY.md` or extend the taxonomy through a new `NBB-501A`-style ticket. This registry updates in lockstep when a new item lands.

- Taxonomy source (locked): `backend/app/studio/TAXONOMY.md`.
- Layer/file patterns (next ticket): `docs/tickets/epics/NBB-005.md#nbb-502`.
- Pilot (next ticket): `docs/tickets/epics/NBB-005.md#nbb-503`.
- Category migrations: `NBB-504` (documents), `NBB-505` (marketing), `NBB-506` (design + logo/brand support), `NBB-507` (learning + media).
