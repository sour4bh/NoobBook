# Clean Code Review — NoobBook (main)

## Scope

| Field         | Value                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| Path          | `/Users/shraman/Documents/dex/NoobBook`                                                                  |
| Commit        | `325461b` on `main`                                                                                      |
| Backend       | Python/Flask — ~60 service files, ~30 util files, 7 API blueprints                                       |
| Frontend      | React/TypeScript — 3-panel workspace, shadcn + Tailwind                                                  |
| Storage       | Supabase (Postgres + Storage + Auth); Pinecone for embeddings                                            |
| LLM surface   | Claude (Sonnet/Haiku) with tool-use agentic loops; OpenAI embeddings; ElevenLabs audio                   |
| Reviewed      | Claude integration, AI services (PDF/PPTX/image), AI agents, main chat, tool executors, persistence,    |
|               | RBAC, task service, Flask blueprints, workspace + chat components                                        |
| Grading lens  | Patterns transferable to greenfield PM-facing "Claude + MCP over internal DBs with SSO/RBAC/audit"       |

---

## Hickey lens

### Where value / identity / state are clearly separated (good)

| Principle                         | File:line                                                           | Observation                                                              |
| --------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Pure value function               | `claude_service.send_message()` `claude_service.py:208-309`         | Takes msgs+config, returns `{content_blocks, model, usage, stop_reason}` |
| Data-oriented namespace           | `claude_parsing_utils.py:50-618`                                    | All fns dict-in / dict-out; duck-types SDK+dict; JSONB round-trip free   |
| Tools as data                     | `app/services/tools/**` via `tool_loader.py:44-76`                  | Add tool = add JSON + executor stanza. Hickey would nod.                 |
| Info-over-methods                 | `auth/permissions.py:25-102` (`DEFAULT_PERMISSIONS`)                | One dict drives DB merges, API, FE types                                 |

### Complecting in chat + message persistence

| Principle                                   | File:line                                              | Observation                                                           | Recommendation                                                                     |
| ------------------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Read/derive/repair/delete complected        | `message_service.py:312-398` (`build_api_messages`)    | Named "build" but also sanitises and DELETEs orphaned rows (L386-392) | Split: pure `load_api_messages()`; explicit `repair_chat_history()` admin call     |
| Error state smuggled into content           | `message_service.py:128-132, 209, 343-357`             | `metadata.error=True` merged into JSONB content; 3 files re-decode    | Add `status`/`error` column or message metadata; stop tagging content              |
| Shape encodes semantics (content polymorph) | `message_service.py:123-139, 185-206, 341-357`        | Content = str / dict-w-text / list-of-blocks / list-of-tool-results   | Add `message_type` column + disciplined per-type schema                            |
|                                             | `chat_service.py:155-211, 244-260` (`_derive_type`)    | Same `isinstance` ladder re-derived in every reader                   |                                                                                    |
| Policy + mechanism tangled                  | `main_chat_service.py:111-188` (`_get_tools`)          | Loads tools, checks permission, routes by source-type in one loop     | Extract pure `ToolRegistry.tools_for(user, project, sources) -> [ToolDef]`         |

### Information vs methods (stateless classes)

```
Pattern: class XService: def __init__(self): ...  singleton at module bottom
Count:   claude_service.py:30   chat_service.py:22   project_service.py:27
         message_service.py:33   source_search_executor.py:26
         memory_executor.py:25   task_service.py:38
Verdict: Stateless classes with singletons; module of functions would be simpler
```

### Singletons + lazy state (identity complected with warmup)

| Site                                             | Lazy state held                                         |
| ------------------------------------------------ | ------------------------------------------------------- |
| `claude_service.py:41-42`                        | `_client`, `_opik_enabled`                              |
| `task_service.py:55-64`                          | `_futures`, `_cancelled_tasks`, `_executor`             |
| `database_executor.py:112`                       | `_conn_cache`                                           |
| `main_chat_service.py:64-69`                     | `_search_tool`, `_memory_tool`, ...                     |
| *Prescription*                                   | Pass clients as params (tiny DI) — don't bake process-wide singletons |

---

## Bernhardt lens

### Functional core — where it exists

| Module                                                           | Purity                                                    |
| ---------------------------------------------------------------- | --------------------------------------------------------- |
| `claude_parsing_utils.py`                                        | Near-perfect pure core. No I/O, no logging, deterministic |
| `cost_tracking._apply_usage` / `_calculate_cost` (`:56-193`)     | Pure numeric; shell wraps with load/save I/O              |
| `utils/text/chunking.py`, `processed_output.py`, `page_markers.py` | All pure                                                |
| `database_executor._validate_readonly_query` (`:81-100`)         | Pure SQL guardrail                                        |

### Imperative shell — where decisions blur with I/O

| Flow                                                | File:line                              | Decisions mixed with I/O                                                        | Refactor target                                                             |
| --------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| PDF extraction pass                                 | `pdf_service.py:267-506`               | Config load, rate-limit, PDF I/O, Claude, parse, upload, summary, metadata      | Pure: `plan_batches(total, tier)`, `assemble_pages(results, meta)`          |
| Web/blog agent loop                                 | `web_agent_service.py:114-194`         | Termination + routing + tokens + log persistence + HTTP in one loop             | Pure `AgentStep.advance(state) -> Decision`; shell `loop_until(terminal)`   |
|                                                     | `blog_agent_service.py:131-220`        | Same pattern repeated                                                           |                                                                             |
| Main chat turn runner                               | `main_chat_service.py:401-646`         | Identity, persist, tool-exec, tokens, error-map (597-604), bg tasks, SSE, API   | Split: `plan_turn` (pure), `run_turn` (shell), `persist_outcome` (shell)    |

### Test surface area

```
Backend tests dir visible? ─── No tests/ under /backend/ in listing
Chat-loop special cases:
  ├── tool_use sanitisation
  ├── empty responses
  ├── partial stream errors
  ├── rate-limit retries
  ├── tool-exec failures
  └── overloaded_error mapping
Currently covered by ─── end-to-end only
With functional core ─── ~80% as fast unit tests
```

---

## Ousterhout lens

### Deep vs shallow modules

| Module                                              | File:line                                       | Depth     | Complexity hidden                                                                   |
| --------------------------------------------------- | ----------------------------------------------- | --------- | ----------------------------------------------------------------------------------- |
| `claude_service.send_message`                       | `:208-309`                                      | Deep      | Retry/backoff, Opik, spend-limit, cost, stream parity. ~10-line sig.                |
| `task_service.submit_task`                          | `task_service.py:97-184`                        | Deep      | 4-call interface hides thread pool + DB tracking + cancellation                     |
| `knowledge_base_service.can_handle` dispatch        | `main_chat_service.py:329-347`                  | Deep      | Chat doesn't care who owns Jira/Notion/MCP tools; copy this                         |
| 13 AI agent services                                | `app/services/ai_agents/*.py` (3911 LOC)        | Shallow   | Same loop skeleton 13x (see diagram)                                                |
| 30 tool executors                                   | `app/services/tool_executors/*` (7505 LOC)      | Shallow   | Pass-through wrappers (`database_analyzer_agent_executor.py` = 39 LOC)              |

### The 13-agent duplication — one shape, 13 copies

```
                           ┌──────────────────────────────────┐
                           │  Claude tool-use loop skeleton   │   <-- ONE algorithm
                           │                                  │
                           │  load config -> load tools ->    │
                           │  init msgs -> MAX_ITERS loop:    │
                           │    send_message(tool_choice=any) │
                           │    accumulate tokens             │
                           │    serialize content blocks      │
                           │    for block if tool_use:        │
                           │      dispatch executor           │
                           │    check termination             │
                           │    append tool_result            │
                           └──────────────────────────────────┘
                                          │
          ┌─────────────┬─────────────┬───┴────────┬──────────────┬────────────┐
          ▼             ▼             ▼            ▼              ▼            ▼
     web_agent     blog_agent     component    business_report  presentation  email_agent
                                   _agent        _agent           _agent
          │             │             │            │              │            │
          ▼             ▼             ▼            ▼              ▼            ▼
   marketing_    prd_agent    wireframe    website_agent   csv_analyzer   database_    freshdesk_
   strategy                    _agent                        _agent       analyzer     analyzer
   _agent                                                                  _agent        _agent

   3911 LOC total. Fixing the "messages must end with user" trap
   (csv_analyzer_agent.py:130-137) requires 13 edits today.
```

### Information hiding / leakage

| Principle                          | File:line                                            | Observation                                                                 | Recommendation                                              |
| ---------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Vendor shape leaks 4 layers        | Anthropic -> `message_service` -> `chat_service` -> FE | `server_tool_use`, `web_search_tool_result`, `web_fetch_tool_result` specials | Store stable `ConversationTurn` domain model; translate at edge |
|                                    | `claude_parsing_utils.py:559-574`                    |                                                                             |                                                             |
| Ingestion detail leaks to routing  | `main_chat_service.py:440-461` (`_file_ext()`)       | `.csv/.database/.freshdesk/.jira/.mixpanel` literals decide tools           | First-class `source_type` enum; chat consumes it            |
| Info hiding done right             | `utils/path_utils.py`                                | Callers never compute `data/projects/{id}/...` paths                        | Keep. (side-effectful auto-mkdir leaks FS policy — minor)   |

#### Content-block shape leakage (cross-layer)

```
┌────────────┐    ┌─────────────────┐    ┌──────────────┐    ┌────────────┐
│ Anthropic  │───▶│ message_service │───▶│ chat_service │───▶│  frontend  │
│    SDK     │    │    (JSONB)      │    │  (formatter) │    │  (parser)  │
└────────────┘    └─────────────────┘    └──────────────┘    └────────────┘
      │                   │                     │                   │
      │                   ▼                     ▼                   ▼
      │             isinstance()            isinstance()       shape checks
      │              ladder                  ladder            per block
      │
      └──── one SDK change (e.g. server_tool_use, web_search_tool_result)
            ripples through all 4 layers
```

### Errors

| Principle                          | File:line                                                          | Observation                                                                  | Recommendation                                             |
| ---------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Ad-hoc per-handler try/except      | `chats/routes.py:37-42, 64-68, 96-101, 146-151, 176-181, 198-204` | Dozens of near-identical `except Exception: return 500`                      | `@app.errorhandler(DomainError)` + `NoobBookError` tree    |
|                                    | `sources/uploads.py:114-118, 196-202, 278-283, 324-328, ...`       |                                                                              |                                                            |
| User-facing error map in wrong layer | `main_chat_service.py:597-604`                                   | Substring match on `"overloaded_error"`, `"rate_limit"` to pick copy         | Pure `friendly_error(exc) -> str` module                   |
| Silent downgrade on auth failure   | `auth/rbac.py:113`                                                 | Catches `Exception`, falls through to dev/single-user mode                   | Log-warn; 401 when `NOOBBOOK_AUTH_REQUIRED=true`           |

### Pass-through methods and thin wrappers

```
┌──────────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│  chat_service.py     │──────▶│   project_service.py │──────▶│   user_service.py    │
│  497 LOC             │       │   ~similar size      │       │   ~similar size      │
│  mostly .table()...  │       │   CRUD wrapping      │       │   CRUD wrapping      │
│  .eq().execute()     │       └──────────────────────┘       └──────────────────────┘
└──────────┬───────────┘
           │  ~20% actual value (table names, message_count join)
           │  ~80% pass-through
           ▼
     Supabase client

Plus: database_connection_service, mcp_connection_service — same shape.
Total > 3000 LOC of CRUD-wrapping with minimal added value.

Upload split across 10 files:
source_upload/{file, url, text, research, database, freshdesk, jira, mcp, mixpanel}_upload.py
 -> Collapse to 1 dispatcher of ~400 LOC keyed on type
SourceService itself re-imports upload_* fns and re-exposes as methods (shallow)
```

### Different is different — abstract the special cases

| Smell                                             | File:line                                | Recommendation                                                            |
| ------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------- |
| 6 parallel `has_*_sources` booleans + 6 if-branches | `main_chat_service.py:440-461, 111-188` | `{source_type -> tool_bundle}` registry; `for t in types: tools += bundle[t]` |
| PDF ≈ PPTX processors (80% copy)                  | `pdf_service.py` (510), `pptx_service.py` (441) | Parameterise or factor `BatchedVisionExtractor` base                      |

### Strategic vs tactical

```
CLAUDE.md lines 554-682: "AI Service Standard Pattern" -- strategic thinking, on paper.
Drift: 13-agent dup, 30 executor files, 10 upload files.
Diagnosis: mild tactical-tornado. No single horrible module — the SAME shape, 10+ times.
Fix cost now <<< fix cost later (especially before the PM project forks the pattern).
```

---

## Top recommendations (ranked)

| #  | Recommendation                                                                                  | Principle tag                              | Effort | Impact |
| -- | ----------------------------------------------------------------------------------------------- | ------------------------------------------ | ------ | ------ |
| 1  | Factor `AgentRunner` out of 13 agent services; each agent becomes ~30-line config               | Ousterhout deep / Bernhardt core           | M      | High   |
| 2  | Define `ConversationTurn` model; translate Anthropic content blocks at edge                     | Ousterhout info-hiding / Hickey decomplect | M      | High   |
| 3  | Replace per-handler `try/except Exception` with `@app.errorhandler(DomainError)` + typed excs   | Ousterhout define-away errors              | S      | High   |
| 4  | Extract `repair_chat_history()` from `build_api_messages()` — reads don't delete rows           | Hickey read/write decomplect / Ousterhout  | S      | High   |
| 5  | `ToolRegistry.tools_for(user, sources)` replaces `_get_tools` policy/mechanism tangle           | Hickey policy vs mechanism / Ousterhout    | S      | Med    |
| 6  | Lift pure `plan_batches` / `detect_missing_pages` / `assemble_processed_output` out of PDF/PPTX | Bernhardt boundaries                       | M      | Med    |
| 7  | Collapse `source_upload/*.py` (10 files) into one `create_source(type, payload)` dispatcher     | Ousterhout pass-through                    | S      | Med    |
| 8  | Replace JSONB ledger columns (`costs`, `memory`, `google_tokens`) with append-only event tables | Hickey identity vs state                   | L      | High   |
| 9  | Keep "Educational Note" docstrings but convert them into named invariants                       | Ousterhout comments = why                  | S      | Low    |
| 10 | Replace 8 coordinated `useState` in `ProjectWorkspace.tsx:50-110` with Zustand/Jotai store      | Ousterhout define-away                     | S      | Med    |

### Recommendation details (anchors)

| #  | File:line anchor                                                                                | Notes                                                                        |
| -- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1  | `app/services/ai_agents/*_service.py` (3911 LOC across 13 files)                                | Interface: `AgentRunner(name, config_loader, tools_loader, executor, termination)` |
| 2  | `message_service.py:185-219, 341-357`; `chat_service.py:155-260`                                | Shape: `{turn_id, role, type: text|tool_call|tool_result|error, payload}`    |
| 3  | `chats/routes.py`, `sources/*.py`, `projects/routes.py`                                          | `NoobBookError` -> `{NotFound, Forbidden, Validation, Upstream}`; audit-friendly |
| 4  | `message_service.py:312-398` (currently swallows exceptions at L386-392)                        | Right now every `get messages` call can mutate DB silently                   |
| 5  | `main_chat_service.py:111-188`                                                                   | `registry.tools_for(user=identity, sources=active_sources) -> List[ToolDef]` |
| 6  | `pdf_service.py:267-506`                                                                         | Today no tests on missing-page / batch-sizing / model-failure recovery       |
| 7  | `app/services/source_services/source_upload/*.py`                                                | Per-type builders consolidated behind single envelope                        |
| 8  | `users.memory`, `users.google_tokens`, `projects.costs`, `projects.memory`                      | `cost_tracking.py:33` already needs a `Lock` — same smell                    |
| 9  | Sanitiser enforces "messages must end with role=user" at `message_service.py:394-398` unnamed    | Name invariants; drop tutorial prose                                         |
| 10 | `ProjectWorkspace.tsx:50-110`                                                                    | `sendingChatIds`, `chatNamesMap`, `openChatId`, `costsVersion`, `sourcesVersion` |

---

## What stands up well

| Pattern                                        | File:line                                                      | Why it works                                                                      |
| ---------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `claude_service` / `claude_parsing_utils` split | `claude_service.py:208-309`, `claude_parsing_utils.py`        | Thin API call, fat pure parser. Retry+backoff, cost, streaming parity, Opik toggle |
| Hybrid source search                           | `source_search_executor.py:50-106`                             | `<1000` tok -> return all; else keyword+semantic. Named thresholds, tunable.      |
| Chunk-based citations                          | `[[cite:{src_id}_page_{n}_chunk_{m}]]` + `GET /citations/{id}` | Stable primary key in prose; tooltip-friendly endpoint                            |
| RBAC shape                                     | `auth/permissions.py:25-224`                                   | `DEFAULT_PERMISSIONS` + `_merge_with_defaults` + `@require_permission`; migration-free |
| Cooperative cancellation                       | `task_service.is_target_cancelled`; used `pdf_service.py:375`  | Correct, simple, reusable for long analytics queries                              |
| Tool defs as JSON                              | `app/services/tools/**` + `tool_loader._validate_tool_definition` | Schema separate from code; version-friendly                                    |
| Tier as data                                   | `config/tier_loader.py` via `get_anthropic_config`             | Single knob (`ANTHROPIC_TIER=1..4`) drives workers + rate limits                  |
| SSE + partial-text preservation                | `main_chat_service.ClaudeStreamError:42-47`, `messages/routes.py:111-168` | Users still see what streamed before a crash; sentinel producer/consumer       |
| Self-healing chat tail (idea, not impl)        | `build_api_messages` sanitiser                                 | Right instinct: don't brick a user's chat on one API error (split write from read though) |
| Masking + validation for API keys              | `api/settings/api_keys.py:53-100+`                             | Real upstream call before save; masked values skipped. Transferable to DB creds.  |
| `can_handle(tool_name)` dispatch               | `main_chat_service.py:329-347`                                 | Chat doesn't know who owns Jira/Notion/MCP tools — registry owns itself           |

---

## Verdict / Rating

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  VERDICT: Overall 5/10                                           │
│                                                                                                  │
│  Working, shippable, feature-rich. Several patterns I'd copy verbatim. Handful of                │
│  duplication/shape-leak problems actively hurting it — agent dup, content-block leakage,         │
│  error sprawl. Nothing incompetent: a product that grew fast, shape-debt is the normal result.   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Lens        | Score   | Bar                               | One-line justification                                                                  |
| ----------- | ------- | --------------------------------- | --------------------------------------------------------------------------------------- |
| Hickey      | 5/10    | ████████████▌                     | Pure-fn islands + clean RBAC, but content complected across 4 layers; JSONB ledgers    |
| Bernhardt   | 4/10    | ██████████▏                       | Some pure cores; load-bearing flows all imperative shell; no visible unit-test suite   |
| Ousterhout  | 5/10    | ████████████▌                     | Deep `claude_service`/`task_service` + can_handle dispatch offset by 13+30+10 shallow  |
| Overall     | 5/10    | ████████████▌                     |                                                                                         |

### Patterns to copy vs avoid (PM/DB greenfield)

| COPY into the new project                                                   | AVOID repeating                                                                |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `claude_service` + `claude_parsing_utils` split as-is                        | One agent-loop implementation per agent                                        |
| Tool definitions as JSON + `tool_loader` validation                          | Anthropic content blocks in your primary database                              |
| `ANTHROPIC_TIER` scale knob for workers/rate limits                          | Side-effecting reads (`build_api_messages` deleting rows)                      |
| `task_service` cooperative cancellation (`is_target_cancelled(target_id)`)   | Ad-hoc `try/except Exception` per route                                        |
| `DEFAULT_PERMISSIONS` + `_merge_with_defaults` + `@require_permission`       | JSONB "ledger" columns (`projects.costs`, `users.memory`, `users.google_tokens`) |
| `connection_users` + `visible_to_all` for per-resource access                | 10 near-identical Supabase CRUD wrappers                                       |
| `[[cite:CHUNK_ID]]` inline citations + dedicated `GET /citations/{id}`       | Per-source-type branching in chat service                                      |
| Hybrid keyword+semantic search with size threshold                           | String-matching Anthropic error messages for UX                                |
| SSE streaming route + partial-text preservation on error                     | Stateless service classes with singleton bottoms                               |
| Masked-key + pre-save-validation for credentials                             | Silent downgrade from auth -> single-user mode (`rbac.py:113`)                 |
| Pure-data tool dispatch via `can_handle(tool_name)` on a registry            |                                                                                |
