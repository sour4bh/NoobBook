# NoobBook — Taste Audit (grounded)

## Context

Audit of `/Users/sour4bh/dev/NoobBook` backend against the `/taste` rules in `~/.claude/CLAUDE.md`: path is the namespace, no ancestor repetition, no cosplay architecture, no vague `utils`/`helpers`, crisp verbs, classes only when they earn their keep. This is the grounded second pass — every claim below is backed by reading the file and its call sites, not by grepping suffixes.

### Scope (locked) — this is Phase A (backend-only)

- Backend only. Frontend (`frontend/`) is out of scope this pass.
- **Phases**: 1 (correctness), 2 (dissolve `utils/`), 3 (domain restructure + targeted service→module + exec pair renames), 5 (type hints + tests + lint rule).
- No HTTP endpoint, DB schema, or external API changes. No new deps beyond `libcst` and `rope` as dev-only for codemods.
- `backend/tests/` must stay green at every commit.

**Deferred cross-stack seams** (explicitly not this pass — a future Phase B):
- **Source status / kind contract** — allowed-extension + category + size-limit logic is mirrored in backend (`file_utils.py`, `source_service.py`) and frontend (`lib/api/sources.ts`, `components/sources/UploadTab.tsx`, `SourceItem.tsx`, `SourcesPanel.tsx`, `SourcesFooter.tsx`, `drive/DriveItem.tsx`). Phase 2 moves `file_utils` to a source-owned home but does not unify with the frontend mirror.
- **Studio job lifecycle** — `studio_signals` table + SSE stream + frontend `StudioPanel` state. Shapes are coupled across stacks; this pass does not change them.
- **Permission matrix** — `backend/app/services/auth/permissions.py:DEFAULT_PERMISSIONS` has a frontend mirror in `useAuth`/`PermissionsContext`. Phase 3 leaves both untouched.
- **Citation `chunk_id` contract** — backend emits `[[cite:chunk_id]]`; frontend parses the same shape. Phase 2 moves `citation_utils` to a source-owned home but does not change the wire format.

### Comment policy (applied during every file touch)

- **Keep**: WHY-comments that explain an LLM pattern — tool-loop invariants (`tool_use` must pair with `tool_result` by ID), chunking rationale (tiktoken used because called thousands of times per source), model choice (Haiku here because speed > quality at this scale), rate-limit math, retry strategy.
- **Strip**: module docstrings like `"""Chat Service - CRUD operations for chat entities."""`, `"""Initialize the chat service."""`, multi-line `"""Educational Note: This service manages chat entity lifecycle…"""` blocks on obvious CRUD, function docstrings that restate the function name.
- **Rewrite**: if a comment existed to explain a bad name, rename instead of keeping the comment.

---

## What the deeper read changed

| Earlier claim (count-based) | Grounded reality |
|---|---|
| "26 paired `*_tool_executor` + `*_agent_executor` are symmetric-folder anti-pattern; merge them." | **Wrong.** The pair is a real architectural layer: `_tool_executor` handles synchronous tool dispatch inside the agentic loop (returns result immediately); `_agent_executor` handles background orchestration (creates `studio_signals` job, launches async task, manages lifecycle). Merging destroys the layer. **Rename for clarity** (e.g. `blog/tool.py` + `blog/run.py`), don't merge. |
| "Aggressive: convert most stateless `*Service` classes to module functions." | **Overreach.** Out of ~89 candidates, only ~7 are actually stateless and worth converting. Most hold real state: Supabase clients, ThreadPoolExecutor, lazy tool definitions, cached prompt configs, mutable `.env` files. The target becomes "drop the suffix where it's pure ancestor-repetition, convert where genuinely stateless, keep the class where it owns something real." |
| "Move `path_utils` to `storage/paths.py`." | **Don't move.** It's the canonical cross-cutting helper (20 domain-specific path builders). Only 3 importers, but they're `app/__init__.py`, `message_service`, `source_service` — core bootstrap. Splitting by domain fragments one canonical source into five, requiring five imports per service. Keep in place. |
| "Move `logger.py` to `auth/` or top-level." | **Keep in `utils/`** (or promote to `app/logger.py`). It's bootstrap-only; `app/__init__.py` is the caller. Moving requires churning the bootstrap path for zero gain. |
| "Merge `claude_parsing_utils` into `integrations/claude/parse.py`." | **Correct, but split into 3**: 30 importers. Splits cleanly into `response_parser.py` (extract_text, extract_tool_use_blocks, is_end_turn) + `content_builder.py` (build_tool_result_content, serialize_content_blocks) + `token_usage.py` (get_token_usage, get_model). |
| "Codemod is safe." | **Confirmed.** No `importlib`/`pkgutil`/`__import__`/string-based registries. Tool loading is file-path-based via `.glob()`. No circular imports between `integrations/` / `ai_services/` / `ai_agents/`. |

---

## Findings (refined)

### Critical

**C1. Ancestor-repetition epidemic** — 63 `*Service` classes, 26 `*Executor` classes (verified counts), plus `Handler`/`Processor`/`Manager` in `tool_executors/`. Worst cases where path + file + class + singleton all echo the same token:
- `services/source_services/source_processing/source_processing_service.py:SourceProcessingService` — "source" appears 4× in the import.
- `services/integrations/claude/claude_service.py:ClaudeService` → `claude_service`.
- `services/chat_services/main_chat_service.py:ChatService` collides with `services/data_services/chat_service.py:ChatService` — same class name, different roles, ambiguous in tracebacks.

**C2. `backend/app/utils/` dumping ground** — 19 files (excluding `text/` subdir and `__init__.py`) mislabeled as utilities. Verified importer counts (right column determines move order and commit ordering):

| file | importers | real domain |
|---|---|---|
| `claude_parsing_utils.py` | **30** | `integrations/claude/` — splits into 3 files |
| `embedding_utils.py` | **15** | splits: local token counter (→ sources) + API counter (→ claude) |
| `source_content_utils.py` | **9** | `services/source_services/` |
| `auth_middleware.py` | **7** | `app/api/auth/` |
| `rate_limit_utils.py` | **4** | `services/ai_services/` (PDF/PPTX/image vision pacing) |
| `encoding_utils.py` | **3** | `services/ai_services/` (base64 for Claude vision) |
| `path_utils.py` | **3** | **stays** — canonical cross-cutting helper |
| `batching_utils.py` | **2** | `services/ai_services/` (PDF/PPTX only) |
| `citation_utils.py` | **1** | `services/source_services/citations.py` (single caller: `api/sources/content.py`; source-chunk domain, not chat) |
| `file_utils.py` | **2** | `services/source_services/file_contract.py` (owns allowed-extension / category / size-limit contract; frontend mirrors it) |
| `presentation_export_utils.py` | **2** | `services/studio_services/` |
| `screenshot_utils.py` | **2** | `services/studio_services/` |
| `excalidraw_utils.py` | **2** | `services/studio_services/wireframe/` |
| `cost_tracking.py` | **2** | `services/integrations/claude/` (pairs with `claude_service`) |
| `logger.py` | **1** | **stays** — bootstrap only (`app/__init__.py`) |
| `pdf_utils.py` | **1** | `services/source_services/pdf/` |
| `pptx_utils.py` | **1** | `services/source_services/pptx/` |
| `docx_utils.py` | **1** | `services/source_services/docx/` |
| `password_utils.py` | **1** | `services/data_services/` (next to user_service) |
| `text/` (subdir) | internal | **stays** — already cohesive |

`backend/app/utils/__init__.py` is empty (no re-export hazard). Every move is a pure find-and-replace on import paths.

**C3. Top-level `services/` split by artifact type, not domain** — `ai_services/`, `ai_agents/`, `tool_executors/`, `studio_services/`, `source_services/`, `data_services/`, `chat_services/`. Confirmed by route-fanout analysis:
- `api/studio/blogs.py` imports from `studio_services/`, `tool_executors/`, `integrations/`, and `auth/` — **4 folders for one feature** (verified). Earlier claim of 6 was wrong. Domain-grouped layout still cuts fanout.
- `api/sources/routes.py` imports from 2 folders; `api/chats/routes.py` from 1 (verified); `api/messages/routes.py` from 2 (verified — `chat_services` + `auth`). For non-studio routes, the benefit is smaller — it's about naming/clarity, not import fanout.

**C4. Paired `*_tool_executor` + `*_agent_executor` — rename, don't merge** (revised from earlier audit):

| Pair | `_tool_executor` role | `_agent_executor` role |
|---|---|---|
| blog | Handles 3 tool calls (`plan`, `generate_image`, `write`) inside agentic loop | Bridges studio signal → job creation → background task launch |
| presentation | Dispatches 4 tools (`plan`, `create_base_styles`, `create_slide`, `finalize`) | Job + agent launch + post-generation PPTX export |
| email, component, business_report, website | Tool dispatch with feature-specific logic (brand overrides, CSV fallback, file tracking) | Studio signal handler + job lifecycle |
| csv_analyzer, freshdesk, database | Synchronous tool dispatch | Background analyzer orchestration |

The convention is real and load-bearing. Fix the naming: inside a `studio/<feature>/` folder, these become `tool.py` (sync tool-loop handler) and `run.py` (background orchestrator), with classes `ToolHandler` and `Runner` or module functions `handle_tool(...)` and `run(...)`.

**C5. 43 `__init__.py` with re-export tricks** (out of 47 total; verified) — violates "Explicit imports; no __init__.py re-export tricks." `backend/app/config/__init__.py` pulls `tool_loader`/`prompt_loader`/`tier_loader` via `__all__`. Most are thin barrels that should be removed in favor of explicit imports at call sites.

### High

**H1. Missing `project_id=` in cost-tracking path** — 47 call-sites of `claude_service.send_message(...)` across 34 files (verified). **16 call-sites across 16 files are missing `project_id=`** — not "several" as earlier claimed. Offenders include `services/ai_services/pdf_service.py`, `services/ai_services/pptx_service.py`, `services/ai_agents/web_agent_service.py`, `services/ai_agents/email_agent_service.py`, others in `ai_agents/`. Silent correctness bug — costs disappear for affected sources.

**H2. Service-class conversion candidates (verified — ~7 clean targets)**

| path | class | singleton | has state? | convert? | reason |
|---|---|---|---|---|---|
| `integrations/supabase/supabase_client.py` | `SupabaseClient` | `get_supabase()` | lazy-init cache only | **yes** | Trivial. One `_client` module var. |
| `integrations/openai/openai_service.py` | `OpenAIService` | `openai_service` | lazy `_client` only | **yes** | Trivial. |
| `ai_services/embedding_service.py` | `EmbeddingService` | `embedding_service` | empty `__init__` | **yes** | Textbook unnecessary class. |
| `app_settings/validation/validation_service.py` | `ValidationService` | `validation_service` | stateless | **yes** | Pure dispatch registry of validators. |
| `ai_services/summary_service.py` | `SummaryService` | `summary_service` | caches `_prompt_config` | **yes** | Module with module-private cache. |
| `ai_services/chat_naming_service.py` | `ChatNamingService` | `chat_naming_service` | stateless | **yes** | Background task trigger + cleanup. |
| `ai_services/video_prompt_service.py` | `VideoPromptService` | `video_prompt_service` | stateless (likely) | **yes** | Single coordinator method. |

**Keep as class** (real state or complexity):
- `ClaudeService` — Opik observability wrapper + streaming + retry/backoff. 33 importers; stability matters.
- `TaskService` — `ThreadPoolExecutor` + `threading.Lock` + futures dict + cancelled set. The canonical example of a class that must stay a class.
- `EnvService` — mutable `.env` file; stateful writes.
- `MainChatService` — 7 lazy-loaded tool definitions + iteration config; core chat loop.
- `MemoryService` — complex merge state.
- `PineconeService` — lightweight state; converting doesn't simplify.
- All 8 `data_services/*` — Supabase client dependency in `__init__`; true DAL.
- All `ai_agents/*` and most `ai_services/*` — tool lazy-load caching + rate-limiter state where present. Low call count means low refactor ROI.
- All `studio_services/*` and `source_services/*` — orchestration state.

**No subclasses** of these classes exist anywhere in the codebase. Polymorphism is not a blocker.

**H3. `execute_tool(...)` verb repeated 15×** — every `*Executor` exposes this. Rename per domain: `search`, `run`, `handle`, etc., following the tool's actual verb.

**H4. N+1 query in `data_services/chat_service.list_chats()` (lines ~56–73)** — one `SELECT count(*)` per chat. Fix with Postgres join or subquery in a single call. Independent of the taste refactor but touches the same file.

### Medium

**M1. Type-hint coverage** — the post-migration `agents/` tree and the code absorbed from `tool_executors/` hover around the same low-to-medium coverage zone. Fill in Phase 5 with `pyright`, starting in `standard` mode and tightening the migrated homes only after the moves land cleanly.

**M2. Silent defaults + broad except** — `data or []`, `request.get_json() or {}`, bare `except Exception:` in `api/chats/routes.py:103`, `api/messages/routes.py:103`. Opik init swallow in `integrations/claude/claude_service.py:89` (that one's fine — optional dep).

**M3. Hardcoded `Path()` in service files** — 14 occurrences despite `path_utils` existing. Worst: `services/tool_executors/presentation_agent_executor.py` (4×), `services/tool_executors/deep_research_executor.py`, `services/ai_services/pptx_service.py`.

**M4. Tautological docstrings** — ~40% of sampled routes/data services. Strip per comment policy during Phase 1–3 file touches.

**M5. Test coverage** — 11 test files for 275 source files. Hot utilities are covered (`claude_parsing_utils`, `chunking`, `cost_tracking`, `storage_service`). Route layer, `main_chat_service`, `ai_agents` have essentially none. Phase 5 adds the two high-value tests: tool-result-pairing invariant and `project_id` enforcement.

### Clean (no action)

- No `lucide-react` stragglers. No manual Claude response parsing (89 disciplined uses of `claude_parsing_utils`). `prompt_loader`/`tool_loader` used consistently. No `importlib`/dynamic imports. No circular imports. 3 TODO markers total (Notion/Jira pagination). `backend/app/utils/__init__.py` is empty.

**Not clean (added after verification)**:
- **`from __future__ import annotations` appears 17 times** in `backend/app/`, including in `database`, `mcp`, and `rbac` modules. The global `~/.claude/CLAUDE.md` forbids this. Strip during Phase 1 or Phase 5; mechanical, low-risk edit.

---

## Execution plan

### Phase 1 — Zero-risk correctness fixes (~2 h, hand-edit)

- **H1**: Add `project_id=project_id` to every `claude_service.send_message(...)` missing it. Files: `pdf_service.py`, `pptx_service.py`, every `ai_agents/*_agent_service.py`, a handful of executors.
- **M3**: Replace hardcoded `Path(...)` in `services/tool_executors/presentation_agent_executor.py`, `deep_research_executor.py`, `services/ai_services/pptx_service.py` with `path_utils` calls.
- **M2**: Replace bare `except Exception:` in `api/chats/routes.py`, `api/messages/routes.py` with targeted exceptions + `logger.exception(...)`. Keep the Opik init `except` (optional dep is a legit use of broad catch).

Verification — do NOT use line-based grep. `rg "claude_service\.send_message\(" | rg -v "project_id"` produces false positives on multi-line calls, `**kwargs` wrappers (e.g. `main_chat_service._call_claude`), and docstrings in `claude_parsing_utils.py`. It also can't verify that a wrapper genuinely forwards `project_id`.

Instead, write a checked-in AST verifier:
```
# backend/scripts/verify_project_id_coverage.py
# Walks every ast.Call whose func qualifies as claude_service.send_message
# (including aliased imports and wrapper functions that re-expose it).
# Reports every call-site missing `project_id=` as a keyword or resolvable
# via a wrapper's **kwargs. Exits 1 on any omission.
```

Run:
```
python backend/scripts/verify_project_id_coverage.py    # expect: "0 omissions"
cd backend && pytest -x
```

### Phase 2 — Dissolve `backend/app/utils/` (~4–6 h, codemod-driven)

**Codemod**: `backend/scripts/refactor/dissolve_utils.py`
1. Reads `MOVE_MAP: dict[old_path, new_path | list[new_path]]` (checked in, reviewable).
2. For each entry: `git mv` the file (or split into multiple target files for `claude_parsing_utils` and `embedding_utils`).
3. Walks every `.py` in `backend/app`, parses with `libcst`, rewrites `from app.utils.X import …` and `import app.utils.X`.
4. Runs `ruff check --fix --select I,F401` on changed files.
5. Runs `pytest -x`.

**Move order** (high-importer first — validates codemod early, leaves narrow-scope files for last):

1. `claude_parsing_utils.py` (30 importers) **split into 3**:
   - `response_parser.py` — `extract_text`, `extract_tool_use_blocks`, `extract_citations`, `is_end_turn`, `get_stop_reason`, `get_text_blocks`, `extract_tool_inputs`
   - `content_builder.py` — `build_tool_result_content`, `build_single_tool_result`, `serialize_content_blocks`, `is_tool_use`
   - `token_usage.py` — `get_token_usage`, `get_model`

   → all three go under `services/integrations/claude/`.

2. `embedding_utils.py` (15 importers) **split into 2**:
   - `services/source_services/tokens.py` — `count_tokens` (tiktoken, hot path for chunking)
   - `services/integrations/claude/token_count.py` — `count_tokens_api` (Claude API call, used for billing/quota)
   - Plus `get_embedding_info`, `get_chunk_config` collocate with `embedding_service` at its new home.

3. `source_content_utils.py` (9) → `services/source_services/content.py`.
4. `auth_middleware.py` (7) → `app/api/auth/middleware.py`.
5. `rate_limit_utils.py` (4) → `services/ai_services/rate_limit.py`.
6. `encoding_utils.py` (3) → `services/ai_services/encoding.py`.
7. `batching_utils.py` (2) → `services/ai_services/batching.py`.
8. `cost_tracking.py` (2) → `services/integrations/claude/cost.py`.
9. `presentation_export_utils.py`, `screenshot_utils.py` (2 each) → `services/studio_services/export/`.
10. `excalidraw_utils.py` (2) → `services/studio_services/wireframe/excalidraw.py`.
11. `file_utils.py` (2 importers: `source_services/source_service.py`, `source_services/source_upload/file_upload.py`) → **`services/source_services/file_contract.py`**. This file owns the allowed-extension / category / size-limit contract for source uploads. The frontend mirrors the same contract in `frontend/src/lib/api/sources.ts`, `components/sources/UploadTab.tsx`, `SourceItem.tsx`, `SourcesPanel.tsx`, `SourcesFooter.tsx`, `drive/DriveItem.tsx`. **Do not bury it under `api/`** — the API layer is just one consumer. Later work can lift this into a cross-stack source-kinds module; deferred (see cross-stack seams).
12. `citation_utils.py` (1 importer: `backend/app/api/sources/content.py`) → **`services/source_services/citations.py`**. It backs the citation API endpoint and performs chunk-metadata lookup by `chunk_id`. The earlier agent's "only message_service uses it" was wrong on re-check. Frontend mirrors the same `[[cite:chunk_id]]` contract. **Source-chunk domain, not chat.** (Note: `utils/text/page_markers.py:14` and `utils/text/processed_output.py:37` mention `citation_utils` in docstrings only — they don't import it.)
13. `pdf_utils.py` (1) → `services/source_services/pdf/pdf_ops.py` (interim; co-located with processor in Phase 3).
14. `pptx_utils.py` (1) → `services/source_services/pptx/pptx_ops.py`.
15. `docx_utils.py` (1) → `services/source_services/docx/docx_ops.py`.
16. `password_utils.py` (1) → `services/data_services/password.py`.
17. `path_utils.py` — **stays**. Add a top-of-file comment flagging it as intentionally cross-cutting.
18. `logger.py` — **stays** (or promote to `app/logging.py`; decide in Phase 3 depending on structure).
19. `text/` subdir — **stays** (cohesive).

After every move, run post-check: `rg "from app\.utils\.<old_name>" backend/app` must return zero lines.

Final state of `backend/app/utils/`: `path_utils.py`, `logger.py`, `text/`. Rename the folder if the remaining files get better homes during Phase 3; otherwise `utils/` shrinks to its legitimate contents.

### Phase 3 — Rename + domain restructure + targeted module conversion (~12–18 h)

Four independent sub-phases, each its own branch:

**3a. Drop `Service` suffix on filenames (mechanical, ~3 h)**
For files where `Service` is pure ancestor-repetition, rename to a **domain noun or operation verb**, not a role label. Rename + update imports. Keep the *class* named for now (handled in 3c). Codemod-driven.

**Bad → Good examples** (role labels like `processor.py`, `service.py`, `handler.py` are also vague names we're trying to leave behind, per the global `/taste` rules):
- `source_processing/source_processing_service.py` → `source_processing/pipeline.py` (noun for the thing) or `source_processing/dispatch.py` (verb for the thing it actually does — route a file to the right processor). **Not** `processor.py` — that's the vague role label we're removing.
- `studio_services/<feature>/<feature>_service.py` → `studio_services/<feature>/<primary-verb>.py` picking the feature's actual operation (e.g. `audio_overview/narrate.py`, `mind_map/build.py`, `presentation/compose.py`). **Not** `service.py`.
- `chat_services/main_chat_service.py` → `chat_services/run.py` or `chat_services/loop.py` (the file owns the agentic loop).

Target pattern: `<dir>/<thing>_service.py` → `<dir>/<domain-verb-or-noun>.py`. Avoid names that collide with stdlib or existing modules. Avoid the vague-verb list (`handle`, `process`, `manage`, `execute`, `perform`, `do`) and vague-role list (`service`, `manager`, `processor`, `handler`, `helper`, `util`).

**3b. Collapse `tool_executors/` into per-feature folders (~4 h)**
The pair is real; the filename is the problem. For each studio feature:
- `studio_services/<feature>/tool.py` — the synchronous tool-loop handler (was `<feature>_tool_executor.py`)
- `studio_services/<feature>/run.py` — the background orchestrator (was `<feature>_agent_executor.py`)
- `studio_services/<feature>/<primary-verb>.py` — the feature's core operation (was `<feature>_service.py`). Pick the feature's actual verb (e.g. `audio_overview/narrate.py`, `blog/write.py`, `presentation/compose.py`). **Do not** use a generic `service.py`.

For standalone executors:
- `source_search_executor.py` → `services/chat_services/tools/source_search.py`
- `memory_executor.py` → `services/chat_services/tools/memory.py`
- `studio_signal_executor.py` → `services/studio_services/signal.py`
- `web_agent_executor.py` → `services/ai_agents/web/tools.py`

Rename `execute_tool(...)` → domain verb per file.

**3c. Convert 7 verified-stateless services to modules (~2 h)**
Each is a small focused commit:

1. `integrations/supabase/supabase_client.py`: `SupabaseClient` class → module functions `get_client()`, `is_configured()`, `reset()` with module-private `_client`, `_initialized`. Update the 20+ callsites (already using `get_supabase()` facade — change negligible).
2. `integrations/openai/openai_service.py`: `OpenAIService` → module `openai` with `_client`, `create_embedding()`, `create_embeddings_batch()`, `get_embedding_dimensions()`.
3. `ai_services/embedding_service.py`: delete class, export `process_embeddings()` directly.
4. `app_settings/validation/validation_service.py`: class → module with `validate(key_name, value)` and per-key validator functions in sibling files.
5. `ai_services/summary_service.py`: class → module with `_prompt_config` lazy cache, `generate_summary(project_id, source_id)`.
6. `ai_services/chat_naming_service.py`: class → module functions.
7. `ai_services/video_prompt_service.py`: class → module functions.

**3d. Top-level layout (do only if 3a/3b/3c merged cleanly; ~4 h)**
Flatten `services/` where it adds clarity:
- `services/studio_services/` → `studio/` (high payoff — route fanout analysis showed 6 folders per feature).
- `services/source_services/` → `sources/`.
- `services/chat_services/` → `chat/`.
- `services/data_services/` → `data/`.
- `services/ai_agents/` → `agents/`.
- `services/integrations/` → `integrations/` (already clean).
- `services/ai_services/` → distribute per domain (PDF → `sources/pdf/`, etc.).
- `services/tool_executors/` already distributed by 3b.
- `services/background_services/` → `background/`.
- `services/app_settings/` → `settings/`.
- `services/auth/` → `auth/`.

Keep `services/` as an intermediate step if collision with existing module names makes the flatten risky. Decide at execution time based on how 3a/3b land.

**3e. Barrel cleanup** — remove `__all__` re-exports from `__init__.py` where they're pure aliasing. Exceptions: `services/integrations/knowledge_bases/` barrel-exports by design; audit per-file.

### Phase 5 — Type hints, tests, lint hook (~4–6 h)

**Precondition**: do not add a tracked Python dependency here. Use a pinned `pyright` CLI invocation via the existing JS toolchain instead. This repo already needs Node for the frontend, so Phase 5 can rely on a one-shot pinned run like `pnpm dlx pyright@1.1.409 --version` (or the current pinned version at execution time) without changing `backend/requirements.txt`.

- Add a checked-in `pyrightconfig.json` at repo root. Start with:
  - `"include": ["backend/app"]`
  - `"typeCheckingMode": "standard"`
  - `"strict": ["backend/app/agents", "backend/app/chat/tools", "backend/app/studio/**/tool.py", "backend/app/studio/**/run.py"]`
  - any narrow excludes needed for generated or intentionally dynamic files
- Run `pnpm dlx pyright@1.1.409` against `backend/app`; fix the reported drift in those migrated targets first, then widen coverage only if the result stays useful. The goal is refactor-safety, not strict-everywhere purity.
- Add `backend/tests/test_main_chat_service_tool_loop.py` pinning the `tool_use` ↔ `tool_result` ID-pairing invariant (including error paths where the executor raises).
- Add `backend/tests/test_claude_cost_tracking.py` — assert that a `send_message` without `project_id` either raises or logs a warning (whichever we choose post-refactor).
- Add a pre-commit check that flags new stateless-singleton classes — prevents `class FooService: def __init__(self): pass; foo_service = FooService()` from creeping back in. Implementation: reuse `backend/scripts/verify_project_id_coverage.py` scaffold with a different AST matcher.

---

## Execution tooling

- **Python AST-safe rewrites**: `libcst` (dev-only). Codemods live under `backend/scripts/refactor/*.py`, reviewable in PR diff, re-runnable.
- **Python renames**: `rope` via a small wrapper script that takes a rename map.
- **Import cleanup**: `ruff check --fix --select I,F401` after every codemod step.
- **File moves**: `git mv` preserves blame.
- **Pre/post-checks**: `rg` queries run before and after each commit (documented per phase).
- **Claude Code role**: author codemods, run them, read failures, patch and re-run. Hand-edit only Phase 1 and anything under 5 files.

### Safety rails

- Branch per phase; commit per logical sub-step. No squashing — blame needs to show why each file moved.
- `pytest -x` after every commit.
- `pytest && bin/dev` smoke check (upload a PDF → chat with citation → studio mind-map → cost increment) after every phase.
- If a codemod breaks tests: **do not `git reset --hard`** — the worktree may contain unrelated edits, and the global rules forbid destructive operations without explicit approval. Non-destructive rollback paths, in order of preference:
  1. Run codemods inside a disposable `git worktree add ../noobbook-refactor-N` so failures can be discarded by removing the worktree.
  2. If running in the primary checkout: `git revert <failed-commit-sha>` to undo the bad commit without touching working-tree changes.
  3. If the failure is mid-commit (unstaged): `git stash` before re-running; re-apply after the codemod is fixed.
  Patch the codemod script, re-run it from clean state. Never hand-fix partial codemod output — it defeats re-runnability.

---

## Critical file touch list

**Phase 1** (manual, ~10 files):
- `services/ai_services/pdf_service.py`, `pptx_service.py`
- `services/ai_agents/web_agent_service.py`, `email_agent_service.py`, and siblings
- `services/tool_executors/presentation_agent_executor.py`, `deep_research_executor.py`
- `api/chats/routes.py`, `api/messages/routes.py`

**Phase 2** (codemod, ~20 file moves + ~80 import-update touches):
- Every file in `backend/app/utils/` except `path_utils.py`, `logger.py`, `text/`.

**Phase 3** (codemod, ~200 file moves + ~275 import-update touches):
- Everything under `backend/app/services/`, with paired executors restructured into per-feature folders.
- Targeted class → module conversions on the 7 verified stateless services.

**Phase 5** (manual/lint-driven, small volume):
- Type hint fills in `ai_agents/` and `tool_executors/`.
- Two new test files.

---

## Reuse existing pieces

- `app/utils/path_utils.py` — stays put; Phase 1 M3 just needs to *use* it.
- `app/utils/claude_parsing_utils.py` — canonical parser; Phase 2 splits it into 3 purpose-specific files but preserves every function name.
- `app/utils/cost_tracking.py:add_usage` — stays the cost hook; moves to `integrations/claude/cost.py`.
- `app/utils/batching_utils.py:create_batches`, `rate_limit_utils.RateLimiter` — the canonical batching/rate-limit primitives; Phase 2 relocates, no rewrites.
- `app/config/prompt_loader.py`, `tool_loader.py`, `tier_loader.py` — already clean; leave the API, move files only if Phase 3d flattening reaches them.

## Verification

**Environment precondition (one-time per checkout)**: backend deps must be installed before any phase gate runs. From a cold checkout, `cd backend && pytest --collect-only -q` fails with `ModuleNotFoundError: No module named 'flask_socketio'` because `tests/conftest.py:7` imports `create_app`, which imports `flask_socketio` at module scope (`app/__init__.py:12`). Run `bin/setup` (or `cd backend && python -m venv venv && . venv/bin/activate && pip install -r requirements.txt && playwright install` on Linux/macOS; the Windows equivalent is documented in the project `CLAUDE.md`). Any verification command below assumes this has completed.

After each phase:
1. `cd backend && pytest -x` — full suite green.
2. Manual smoke: `bin/dev` → upload PDF → chat with citation question → verify `[[cite:...]]` tooltip resolves → trigger a studio mind-map → confirm `GET /api/v1/projects/{id}/costs` increments.
3. Phase 2 post-check: `rg "from app\.utils\.(claude_parsing|embedding|cost_tracking|...)" backend/app` returns zero (for every moved file).
4. Phase 3 post-check: `rg "from app\.services\." backend/app` returns only imports consistent with the new layout.
5. Phase 1 post-check: `python backend/scripts/verify_project_id_coverage.py` reports zero omissions. (The line-based grep equivalent is unreliable — see the Phase 1 verification note.)

## Out of scope

- No HTTP endpoint paths or request/response shapes change.
- No Supabase schema, RLS, or migration changes.
- No dependency additions (except dev-only `libcst`, `rope`).
- No new features; no refactor toward a new architecture pattern.
- Frontend (`frontend/`) untouched this pass — findings recorded for later.
- `docker/`, deployment config, CI untouched.

## Intentional exceptions to `/taste`

- `backend/app/api/*/routes.py` naming kept — Flask blueprint convention + project CLAUDE.md mandate.
- `backend/app/config/` loaders keep their `*_loader` names — they describe a real role.
- `backend/app/utils/path_utils.py` and `logger.py` stay in `utils/` — verified cross-cutting / bootstrap use.
- `__init__.py` in `services/integrations/knowledge_bases/` may keep barrel exports if they act as deliberate boundaries (audit per-file in Phase 3e).
- `ClaudeService`, `TaskService`, `EnvService`, `MainChatService`, `MemoryService`, all `data_services/*`, all `ai_agents/*` keep their class form — verified real state.

---

## Corrections from verification pass

The first-pass audit cited several numbers that failed a skeptical re-grep. Corrected in the body above; logged here for traceability:

| Claim (original) | Actual | Source |
|---|---|---|
| ~89 `*Service` classes | **63** | `rg "^class [A-Z][a-zA-Z]*Service[(:]" backend/app -c` |
| 33 `claude_service.send_message(` call-sites | **47 calls across 34 files** | `rg "claude_service\.send_message\(" backend/app` |
| "several files" missing `project_id=` | **16 files, 16 calls** | per-file inspection |
| 44 `__init__.py` re-export tricks | **43 with re-exports out of 47 total** | `rg "^__all__|^from \." __init__.py files` |
| 9 paired tool/agent executors | **10 pairs** (10 `*_tool_executor.py` + 10 `*_agent_executor.py`) | `ls services/tool_executors/` |
| 20 files in `utils/` | **19 files** (excl. `text/`, `__init__.py`) | `ls backend/app/utils/` |
| `logger.py` has 2 importers | **1 importer** (`app/__init__.py`) | `rg -l "from app.utils.logger"` |
| `api/studio/blogs.py` imports from 6 folders | **4 folders** (studio_services, tool_executors, integrations, auth) | direct read |
| `api/messages/routes.py` imports from 1 folder | **2 folders** (chat_services, auth) | direct read |
| "No `from __future__ import annotations`" | **17 instances** — moved from Clean to Not-clean section | `rg "from __future__" backend/app` |

All other numeric claims verified ✓: importer counts for `claude_parsing_utils` (30), `embedding_utils` (15), `source_content_utils` (9), `auth_middleware` (7), `rate_limit_utils` (4), `encoding_utils` (3), `path_utils` (3), `cost_tracking` (2); `*Executor` count (26); `execute_tool(` method count (15); `data_services/` count (8); `path_utils` function count (20); `backend/app/` total `.py` files (275). Service-state reads for `embedding_service`, `validation_service`, `summary_service`, `task_service`, `supabase_client` all match the assessment.

## Verification log (grounding for this document)

- Service-class audit: read `claude_service.py`, `supabase_client.py`, `storage_service.py`, `openai_service.py`, `pinecone_service.py`, `task_service.py`, `env_service.py`, `validation_service.py`, `summary_service.py`, `embedding_service.py`, `chat_naming_service.py`, `main_chat_service.py`, `memory_service.py`, all `data_services/*` end-to-end. Singleton counts, state assessments, and importer counts listed above are from those reads.
- Paired executor audit: read the tool/agent pair for blog, presentation, email, component, business_report, website, csv_analyzer, freshdesk, database. Confirmed the tool-executor-vs-agent-executor layering is real and intentional.
- Dynamic-import audit: greps for `importlib`, `__import__`, `pkgutil`, `TOOL_REGISTRY`. Only `.glob()`-based file discovery found in `tool_loader.py`, `prompt_loader.py`, `message_service.py`. Codemod-safe.
- Circular-import audit: verified one-way direction `ai_services/` → `integrations/`, `ai_agents/` → `integrations/`. No cycles.
- Route fanout audit: `api/sources/`, `api/messages/`, `api/chats/`, `api/projects/`, three `api/studio/*` routes. Studio routes touch 6+ service folders per feature; other routes touch 1–2.
