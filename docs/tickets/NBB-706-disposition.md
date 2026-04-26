# NBB-706 Suffix-Drift Disposition Inventory

Audit of every `*Service` and `*Executor` class in `backend/app/` against
the NBB-706 Keep-as-class list, the seven stateless conversion targets,
and any holdouts that an upstream ticket missed. Required deliverable per
NBB-706 AC#3.

Disposition values:
- `KEEP` — legitimate exception per NBB-706 Keep-as-class list (provider,
  store, orchestration). Stateful or has explicit platform contract.
- `CONVERTED-IN-NBB-706` — converted in this ticket per the seven-row
  stateless conversion map.
- `MOVED-IN-NBB-803` — kept or converted by NBB-706, then moved out of
  `services/` by the NBB-008 continuation epic.
- `MOVED-IN-NBB-804` — kept by NBB-706, then moved out of `services/` and
  converted to chat-owned module functions by the NBB-008 continuation epic.
- `MOVED-IN-NBB-805` — kept or converted by NBB-706, then moved to
  `settings/` by the NBB-008 continuation epic.
- `MOVED-IN-NBB-806` — kept or converted by NBB-706, then moved to
  `providers/` by the NBB-008 continuation epic.
- `MOVED-IN-NBB-807` — kept by NBB-706, then moved to `connectors/` by
  the NBB-008 continuation epic.
- `HOLDOUT` — should have been converted upstream; if the blast radius is
  small enough this ticket fixes it manually, otherwise the upstream
  owner is named.

## *Service classes (33)

| Path | Class | Disposition | Rationale |
|---|---|---|---|
| backend/app/background/tasks.py | TaskService | KEEP | `ThreadPoolExecutor`, lock, futures dictionary, and cancellation state. Per NBB-706 Keep-as-class list. |
| backend/app/sources/link/agent.py | WebAgentService | MOVED-IN-NBB-803 | Agentic loop orchestration; lazy tool definitions, MAX_ITERATIONS. Kept as a class per NBB-706, then moved to source-owned link extraction by NBB-803. |
| backend/app/services/ai_services/chat_naming_service.py | ChatNamingService | CONVERTED-IN-NBB-706 | Row 6: class deleted; behavior inlined into `app/chat/naming.py` (NBB-302's domain home). |
| backend/app/sources/embedding.py | EmbeddingService | MOVED-IN-NBB-803 | Row 3: class deleted in NBB-706; module-level functions exposed (`process_embeddings`, `delete_embeddings`, `search_similar`). Moved from `services/ai_services` to source-owned embedding by NBB-803. |
| backend/app/sources/image/extract.py | ImageService | MOVED-IN-NBB-803 | Stateful: `_tool_definition`, `_prompt_config`, `_tier_config` lazy caches. Kept as a class per NBB-706, then moved to source-owned image extraction by NBB-803. |
| backend/app/chat/memory/merge.py | MemoryService | MOVED-IN-NBB-804 | Per NBB-706 Keep-as-class list: merge behavior and stateful memory policy. NBB-804 moved it to chat-owned memory and exposed module functions. |
| backend/app/sources/pdf/extract.py | PDFService | MOVED-IN-NBB-803 | Stateful: lazy tool/prompt config, ThreadPoolExecutor, batched extraction state. Kept as a class per NBB-706, then moved to source-owned PDF extraction by NBB-803. |
| backend/app/sources/pptx/extract.py | PPTXService | MOVED-IN-NBB-803 | Stateful: lazy tool/prompt config, ThreadPoolExecutor, batched extraction state. Kept as a class per NBB-706, then moved to source-owned PPTX extraction by NBB-803. |
| backend/app/sources/summary.py | SummaryService | MOVED-IN-NBB-803 | Row 5: class deleted in NBB-706; module-level `generate_summary` exposed with `_prompt_config` preserved as module-private lazy cache. Moved from `services/ai_services` to source-owned summaries by NBB-803. |
| backend/app/services/ai_services/video_prompt_service.py | VideoPromptService | CONVERTED-IN-NBB-706 | Row 7: class deleted; module renamed to `app/studio/media/video/prompt.py` per ticket body in-scope rename; `generate_video_prompt` exposed as module function. AST allowlist entry dropped in same commit. |
| backend/app/settings/env.py | EnvService | MOVED-IN-NBB-805 | Per NBB-706 Keep-as-class list: mutable `.env` writes and reload behavior. Moved from `services/app_settings` by NBB-805. |
| backend/app/settings/validation.py | ValidationService | MOVED-IN-NBB-805 | Row 4: class deleted; `validate(key_name, value)` exposed as module function with per-key validator function dispatch. Moved from `services/app_settings/validation/validation_service.py` by NBB-805. |
| backend/app/providers/anthropic/messages.py | ClaudeService | MOVED-IN-NBB-806 | Per NBB-706 Keep-as-class list: provider observability, streaming, retry/backoff, and broad call-site stability. |
| backend/app/providers/elevenlabs/audio.py | AudioService | MOVED-IN-NBB-806 | Stateful: API key/cached config; provider lifecycle. |
| backend/app/providers/elevenlabs/transcription.py | TranscriptionService | MOVED-IN-NBB-806 | Stateful: API key/cached config; provider lifecycle. |
| backend/app/providers/elevenlabs/tts.py | TTSService | MOVED-IN-NBB-806 | Stateful: API key/cached config; provider lifecycle. |
| backend/app/connectors/freshdesk/client.py | FreshdeskService | MOVED-IN-NBB-807 | Stateful connector client (cached config, reload_config hook). |
| backend/app/connectors/freshdesk/sync.py | FreshdeskSyncService | MOVED-IN-NBB-807 | Per NBB-706 Keep-as-class allowlist: connector orchestration (Freshdesk sync lifecycle). |
| backend/app/providers/google/auth.py | GoogleAuthService | MOVED-IN-NBB-806 | Stateful: OAuth credential lifecycle and token refresh. |
| backend/app/connectors/google_drive/files.py | GoogleDriveService | MOVED-IN-NBB-807 | Stateful Google Drive connector API client lifecycle. |
| backend/app/providers/google/imagen.py | ImagenService | MOVED-IN-NBB-806 | Stateful: API client lifecycle. |
| backend/app/providers/google/veo.py | GoogleVideoService | MOVED-IN-NBB-806 | Stateful: API client lifecycle. |
| backend/app/connectors/jira/client.py | JiraService | MOVED-IN-NBB-807 | Stateful connector client (cached config, reload_config hook). |
| backend/app/connectors/knowledge.py | KnowledgeBaseService | MOVED-IN-NBB-807 | Tool registry/lifecycle and per-connector routing state. |
| backend/app/connectors/mixpanel/client.py | MixpanelService | MOVED-IN-NBB-807 | Stateful connector client (cached config, reload_config hook). |
| backend/app/connectors/notion/client.py | NotionService | MOVED-IN-NBB-807 | Stateful connector client (cached config, reload_config hook). |
| backend/app/connectors/mcp/tools.py | McpToolService | MOVED-IN-NBB-807 | Per NBB-706 Keep-as-class allowlist: MCP tool registry/lifecycle. |
| backend/app/providers/openai/embeddings.py | OpenAIService | MOVED-IN-NBB-806 | Row 2: class deleted; module-level embedding functions preserved after provider move. |
| backend/app/providers/pinecone/index.py | PineconeService | MOVED-IN-NBB-806 | Per NBB-706 Keep-as-class list: provider client lifecycle. |
| backend/app/providers/supabase/auth.py | AuthService | MOVED-IN-NBB-806 | Stateful: Supabase admin client wrapper, bootstrap hooks. |
| backend/app/providers/tavily/search.py | TavilyService | MOVED-IN-NBB-806 | Stateful provider client. |
| backend/app/providers/youtube/transcript.py | YouTubeService | MOVED-IN-NBB-806 | Stateful provider client (proxy config, transcript fetch lifecycle). |
| backend/app/sources/analysis/csv/summarize.py | CSVService | KEEP | Stateful: lazy prompt/tools cache; agentic loop orchestration. Source orchestration class kept per NBB-706 Keep-as-class list. |

## *Executor classes (9)

| Path | Class | Disposition | Rationale |
|---|---|---|---|
| backend/app/chat/memory/run.py | MemoryExecutor | KEEP | Per NBB-706 Keep-as-class allowlist: chat memory orchestration. Module renamed from `chat/memory/store.py` to `chat/memory/run.py` in NBB-706 §3 (chat shadow fix); the AST allowlist tuple was updated in the same commit. |
| backend/app/sources/analysis/csv/run.py | AnalysisExecutor | KEEP | Stateful: agentic loop orchestration; lazy tool/prompt config; iteration cap. Source orchestration class kept per NBB-706 Keep-as-class list. |
| backend/app/sources/analysis/csv/tool.py | CSVToolExecutor | KEEP | Per NBB-706 Keep-as-class allowlist: CSV analysis tool runtime. |
| backend/app/sources/analysis/database/tool.py | DatabaseExecutor | KEEP | Stateful: connection resolver and lazy schema introspection. Source orchestration class kept per NBB-706 Keep-as-class list. |
| backend/app/sources/analysis/freshdesk/tool.py | FreshdeskExecutor | KEEP | Stateful: agentic search loop with iteration cap. Source orchestration class kept per NBB-706 Keep-as-class list. |
| backend/app/sources/analysis/research/tool.py | DeepResearchExecutor | KEEP | Per NBB-706 Keep-as-class allowlist: deep research agent runtime. |
| backend/app/sources/link/run.py | WebAgentExecutor | KEEP | Per NBB-706 Keep-as-class allowlist: web agent runtime for link sources. |
| backend/app/sources/search.py | SourceSearchExecutor | KEEP | Per NBB-706 Keep-as-class allowlist: hybrid keyword+semantic search runtime. |
| backend/app/studio/signal/__init__.py | StudioSignalExecutor | KEEP | Per NBB-706 Keep-as-class allowlist: signal emission/ack runtime. Moved from `studio/signal.py` during NBB-810 so the signal tool schema can live under `studio/signal/tools/`. |

## Summary

- Total classes in inventory: 42 (33 *Service + 9 *Executor).
- KEEP: 11 (2 *Service + 9 *Executor).
- MOVED-IN-NBB-803: 6 *Service rows.
- MOVED-IN-NBB-804: 1 *Service row.
- MOVED-IN-NBB-805: 2 *Service rows.
- MOVED-IN-NBB-806: 12 *Service rows.
- MOVED-IN-NBB-807: 7 *Service rows.
- CONVERTED-IN-NBB-706 (matched by the *Service grep): 2 — `ChatNamingService`
  and `VideoPromptService`.
- HOLDOUTS: 0.
- The seventh NBB-706 conversion target (`SupabaseClient`) carries a `Client`
  suffix and is invisible to the inventory greps. It is logged in the
  Supplemental row below for completeness.

## Supplemental: non-suffix class also converted in NBB-706

| Path | Class | Disposition | Rationale |
|---|---|---|---|
| backend/app/providers/supabase/client.py | SupabaseClient | MOVED-IN-NBB-806 | Row 1: class deleted; `get_client()`, `is_configured()`, `reset()` exposed as module functions; `_client`, `_initialized` preserved as module-private state after provider move. |

The 42 inventory rows above cover the AC#3 deliverable; SupabaseClient is logged here for completeness because the seventh conversion target uses a `Client` suffix instead of `Service` and would be missed by the inventory greps.

## Deleted residue after NBB-706

| Path | Class | Disposition | Rationale |
|---|---|---|---|
| backend/app/services/ai_services/wireframe_service.py | WireframeService | DELETED-IN-NBB-802 | Dead residue from the studio wireframe migration; live behavior is in `backend/app/studio/design/wireframe/draw.py`. |
