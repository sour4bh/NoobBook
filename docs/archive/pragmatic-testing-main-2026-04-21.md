# Pragmatic Testing Review — NoobBook (main)

## Scope

Whole-codebase review of `/Users/shraman/Documents/dex/NoobBook` at branch `main` (HEAD `325461b`).

### Suite inventory

| Tier     | Framework                                                      | Files | Tests | Test LoC | Prod LoC | Ratio  | CI   |
| -------- | -------------------------------------------------------------- | ----- | ----- | -------- | -------- | ------ | ---- |
| Backend  | `pytest==9.0.1` + `pytest-flask==1.3.0` + `unittest.mock`      |     9 |   256 |    1,894 |   59,524 |  3.2%  | None |
| Frontend | none (no vitest / jest / RTL / playwright / cypress / msw)     |     0 |     0 |        0 |   41,848 |  0.0%  | None |
| E2E      | none (no Playwright / Cypress / Selenium anywhere)             |     0 |     0 |        0 |      n/a |   n/a  | None |
| CI       | none (no `.github/workflows/`, `.circleci/`, Makefile, hooks)  |   n/a |   n/a |      n/a |      n/a |   n/a  | None |

Shared fixtures: `backend/tests/conftest.py:1-52`. Frontend verified at `frontend/package.json:6-11, 76-93`.

Review surface: every file in `backend/tests/`, `conftest.py`, every sub-package under `backend/app/services/`,
`backend/app/api/`, and `backend/app/services/auth/`. Risk cross-referenced with product surface in `CLAUDE.md`
(agentic chat loop, RAG source search, studio generation, multi-modal ingestion, RBAC, MCP, cost tracking, memory).

## Test pyramid — observed shape

```
Healthy pyramid                       NoobBook (observed)
                                      (inverted cone — top-heavy gap)
        /\                                ┌─────────────────────────────┐
       /E2\                               │  E2E: 0                     │   <- entire tier missing
      /----\                              ├─────────────────────────────┤
     /  IT  \                             │  INTEGRATION: 0             │   <- entire tier missing
    /--------\                            │  (no HTTP, no DB, no MCP)   │
   /  UNIT    \                           ├─────────────────────────────┤
  /____________\                          │  UNIT: 256 (pure funcs only)│   <- narrow sliver
                                          │  chunking / citations /     │
                                          │  parsing / pricing / text   │
                                          └─────────────────────────────┘
                                                Frontend tier: not drawn — 0 tests
```

## Load-bearing tests (keep)

| File                                      | Tests | What it covers                                                                          | Principle tag                                                                             | Why it earns its keep                                                                |
| ----------------------------------------- | ----- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `test_chunking.py`                        |    28 | `parse_processed_text`, `_split_text_into_token_chunks`, `_split_into_sentences`, `_split_long_sentence`, `chunks_to_pinecone_format` | [Fowler — refactoring safety net], [Shore — fast, sociable, test what user cares about]   | Pure fns, no mocks, boundary cov (empty, page-0, UUIDs w/ hyphens, preserve under split at `test_chunking.py:137-144`). RAG invariant layer. |
| `test_citation_utils.py`                  |    17 | `parse_chunk_id`, `extract_citations_from_text`                                         | [Beck — tests drive right API], [Meszaros — minimal fixture, no mystery guest]            | Pure text parsing; UUID-with-hyphens edge at `test_citation_utils.py:22-34`. User-facing regression = every response corrupted. |
| `test_claude_parsing_utils.py`            |    63 | `is_tool_use`, `is_end_turn`, `extract_text`, `extract_tool_use_blocks`, `build_tool_result_content`, `serialize_content_blocks` | [Fowler — contract test at SDK boundary], [Shore — don't mock code you don't own]         | Tests BOTH dict AND SDK-object (`SimpleNamespace`) inputs at `test_claude_parsing_utils.py:105-132`. SDK-seam, catches silent bumps. |
| `test_cost_tracking.py`                   |    24 | `_get_model_key`, `_calculate_cost`, `_ensure_cost_structure`                           | [Beck — small, exact], [Farley — deterministic]                                           | Hardcoded $3/$15 Sonnet, $1/$5 Haiku at `test_cost_tracking.py:59-79`. Billing-adjacent, stops silent overcharging. |
| `test_text_utils.py`                      |    56 | `build_processed_output`, `clean_text_for_embedding`, `clean_chunk_text`, `normalize_whitespace`, `build_page_marker`, `find_all_markers` | [Fowler — contract test], [Beck — pinning invariant]                                      | Anchors `=== TYPE PAGE N of M ===` grammar; `test_text_utils.py:275-280` loops every `SOURCE_TYPES`. Grammar change breaks every chunker/retriever/summariser at once. |
| `test_batching_and_rate_limit.py` (core)  |   n/a | `create_batches`, `get_batch_info`, `RateLimiter` counter/window                        | [Fowler — tested at algorithm level, not wall-clock]                                      | Batching clean; `remaining_requests` after N calls + window reset correct. (Rate limiter half has smell — see below.) |

## Tests that don't pay rent

| File:line                                                               | Smell                                                          | Principle tag                                                                                  | Recommendation                                                                                                                                            |
| ----------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_storage_service.py:109-150` (`TestListLimitOptions`)              | Tautology — asserts mock sees the kwarg the code passed        | [Meszaros — Testing implementation, not behavior], [Shore — never mock things you don't own]   | Delete. Bug 2 was "Supabase silently truncates at 100" — mock echoes the kwarg, will pass if Supabase renames it. Replace with contract test vs real client or integration env. |
| `test_deep_research_agent.py:42-76` (`test_works_with_output_path`)     | Over-mocked AND self-contradictory                             | [Meszaros — Obscure Test, Fragile Test], [Shore — solitary unit hides contradiction]           | Mock returns `stop_reason: "end_turn"` yet line 74 expects `"maximum iterations"` error. Lines 47-56 assign to private `agent._prompt_config` / `agent._tools`, skipping `prompt_loader`/`tool_loader`. Rewrite via `@patch` on loader surface; fix semantics or remove. |
| `test_batching_and_rate_limit.py:126-164` (window-reset siblings)       | Mystery Guest — pokes `limiter._minute_start_time = t-61`      | [Beck — tests should drive better API], [Meszaros — Obscure Test via private-state access]     | Extract clock seam: `clock: Callable[[], float] = time.time`, inject fake. Stop freezing private attr names.                                              |
| `test_website_tool_executor.py:23-36` (`TestGetContentType`)            | Eager test / low-value — verifies a dict lookup                | [Meszaros — Eager test / low-value]                                                            | Delete. The data is the test.                                                                                                                             |
| `backend/tests/conftest.py:10-20` (`app`, `client` fixtures)            | Obsolete Setup / dead code — zero tests consume them            | [Meszaros — Obsolete Setup]                                                                    | Either delete, or write the HTTP endpoint tests they were meant to enable.                                                                                 |

## Missing coverage that matters (ranked risk matrix)

| Rank | File                                                                                | Prod LoC | Tests | Risk surface                                                                                                 | Consequence if broken                                                                                           |
| ---- | ----------------------------------------------------------------------------------- | -------- | ----- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
|    1 | `backend/app/services/tool_executors/database_executor.py`                          |      770 |     0 | `_validate_readonly_query`, `_UNSAFE_SQL_KEYWORDS_RE` (`database_executor.py:41-43`), `_quote_identifier` (`:36`), `;` stacking (`:89`) | Arbitrary SQL via Claude → exfiltration / corruption. The exact code the PM-DB greenfield project is about to re-implement. |
|    2 | `backend/app/services/integrations/mcp/mcp_client.py`                               |      487 |     0 | `_validate_stdio_command`, `SHELL_METACHAR_PATTERN`, `BLOCKED_ENV_KEYS` (`PATH`, `LD_PRELOAD`, `DYLD_INSERT_LIBRARIES`), `_build_headers`, `_connect` | RCE-adjacent. Allowlist + env-bypass protection. Will speak MCP to internal DBs.                                |
|    3 | `backend/app/services/auth/rbac.py`                                                 |      239 |     0 | `require_admin`, `require_auth`, `require_permission`, `get_request_identity`; 3 identity paths (JWT / dev headers / single-user); `NOOBBOOK_AUTH_REQUIRED` toggle | (a) dev headers accepted in prod (no auth-required check before trusting `X-NoobBook-User-Id` at `rbac.py:116-125`); (b) `_load_role_from_users_table` swallows exceptions, silently downgrades role (`rbac.py:81-82`); (c) `is_auth_required()` default-true flipped. |
|    4 | `backend/app/services/auth/permissions.py`                                          |      347 |     0 | `user_has_permission`, NULL-means-all-enabled JSONB semantics                                                | `@require_permission("data_sources", "database")` gates PM-relevant SQL execution. Untested gate.               |
|    5 | `backend/app/services/chat_services/main_chat_service.py`                           |      713 |     0 | Whole tool-use loop (`MAX_TOOL_ITERATIONS = 10`), `_build_system_prompt`, per-user MCP injection, dispatch for `search_sources` / `store_memory` / `analyze_csv_agent` / `analyze_database_agent` / `studio_signal` | Loop termination, per-iter memory pollution, error bubbling, MCP registry handoff — all unverified. Smoke test (tool_use → tool_use → end_turn) would catch dozens of regressions. |
|    6 | `backend/app/services/tool_executors/source_search_executor.py`                     |      433 |     0 | Hybrid search: small-source all-chunks; `difflib.SequenceMatcher` fuzzy keyword; Pinecone semantic; `chunk_id` dedup. Knobs: `SMALL_SOURCE_THRESHOLD = 1000`, `FUZZY_THRESHOLD = 0.7`, `DEFAULT_TOP_K = 5` | Thresholds will get "tuned" in a hurry. No way to detect citation-precision regressions. [Fowler — changeability] |
|    7 | All HTTP endpoints (`api/sources`, `api/chats`, `api/messages`, `api/projects`, `api/settings`, `api/auth`) |    4,416 |     0 | Zero `client.get/post/put/delete` anywhere in `backend/tests/`. `api/settings/api_keys.py` (595 LoC) handles `***`-prefix secret masking + admin gates | Routing, blueprint wiring, RBAC decorators in prod config, JSON envelopes, cross-layer failures — unverified.    |
|    8 | Source processors (`source_services/source_processing/{pdf,pptx,image,audio,docx,youtube,link,csv,database,mixpanel,freshdesk,jira,mcp}_processor.py`) | varies (16 files) | 0 | Each has own retry / batching / status-transition semantics. `=== TYPE PAGE N of M ===` producers on trust (only consumers `test_chunking.py` / `test_text_utils.py` verify) | PDF/PPTX batched-extraction invariants unchecked at producer side.                                               |
|    9 | Cost tracking side-effects                                                          |      n/a |     — | `test_cost_tracking.py` verifies math but never that `claude_service.send_message(..., project_id=...)` writes to `projects.costs` in Supabase | Integration between pricer and store vouched by code review only.                                               |

## Test smells

| Smell                                  | File:line                                                                                                       | Example                                                                                                                         | Fix                                                                                  |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Mystery Guest / private-state reach    | `test_batching_and_rate_limit.py:133, 139, 160`; `test_deep_research_agent.py:47-55`                            | `limiter._minute_start_time = time.time() - 61`; assigns `agent._prompt_config`, `agent._tools` directly                        | Inject a clock (`clock: Callable[[], float] = time.time`); `@patch` loader surface.  |
| Fragile Test via mocked-infra echo     | `test_storage_service.py::TestListLimitOptions`                                                                 | Asserts on `mock.call_args` kwarg name `options`                                                                                | Replace with contract test against real client or a recorded cassette.              |
| Eager Test                             | `test_storage_service.py::TestDeleteUserBrandAssets::test_recurses_into_folders`                                | 5 assertions across 3 dimensions (result, `remove.assert_called_once`, 3 path substrings, length) in one test                   | Split: one assertion per behavior. One failure should not mask the others.           |
| Conditional logic in test (`or`-chain) | `test_storage_service.py:119-122`                                                                               | `call_args[1].get("options") == _LIST_OPTIONS or (len(call_args[0]) > 1 and call_args[0][1] == _LIST_OPTIONS) or call_args.kwargs.get("options") == _LIST_OPTIONS` | Pin the interface. An interface tests can't pin is an interface that will drift. [Osherove] |
| Obscure Test / self-contradictory      | `test_deep_research_agent.py:73-76`                                                                             | Mock returns `end_turn`; test expects `"maximum iterations"` error                                                              | Either agent must handle `end_turn` as termination, or test is wrong. Resolve — don't bake in confusion. |
| No hermeticity infrastructure          | repo root                                                                                                       | No `pytest.ini` / `pyproject.toml` markers, no coverage threshold, no parallelism config, no CI                                 | Add `pyproject.toml` with `[tool.pytest.ini_options]`, coverage gates, GitHub Actions on every PR. [Farley — run in minutes on every push] |
| Test data duplication / missing builder| `test_claude_parsing_utils.py` helpers `_sdk_text`, `_sdk_tool_use`, `_dict_text`                                | Reinvented `SimpleNamespace(type="text", text=…)` pattern                                                                       | Extract to shared `tests/support/anthropic_fixtures.py` for reuse across agent tests.|
| Regression-only pattern (not TDD)      | `test_storage_service.py:5-6, 32, 36, 106`; `test_website_tool_executor.py:6, 39`; `test_deep_research_agent.py:5` | 5 of 9 files announce "Bug N regression"                                                                                        | Fine as pinning, but leaves un-bugged-yet areas uncovered. Pair with forward-looking tests. [Beck — NOT TDD] |

## Verdict

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  RATING: 3 / 10                                                                          │
│                                                                                          │
│  Thin, mostly-sound unit layer over 60 KLoC backend + 42 KLoC frontend with:             │
│    - no CI                                                                               │
│    - no frontend tests                                                                   │
│    - no e2e                                                                              │
│    - zero coverage on the three surfaces that matter most for the greenfield project:    │
│        * authz (rbac.py / permissions.py)                                                │
│        * SQL executor (database_executor.py)                                             │
│        * MCP transport (mcp_client.py)                                                   │
│                                                                                          │
│  What exists is honest — no tautologies-as-theater, no massive mock scaffolds pretending │
│  to test flows. But it is nowhere close to "ship-and-refactor-safely" territory.         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### Score breakdown

| Dimension                                    | Score | Note                                                                                               |
| -------------------------------------------- | ----- | -------------------------------------------------------------------------------------------------- |
| Pure-function unit coverage                  |  7/10 | Chunking, citations, parsing, pricing, text — honest, mock-free, boundary-aware                    |
| Integration coverage (HTTP / DB / MCP)       |  0/10 | Zero `client.*` calls, zero DB integration, zero MCP contract tests                                |
| E2E coverage                                 |  0/10 | Playwright listed as system dep in `CLAUDE.md`, never used                                         |
| Authz & security-critical coverage           |  0/10 | rbac / permissions / SQL validator / MCP stdio allowlist — all 0 tests                             |
| Frontend coverage                            |  0/10 | No vitest / jest / RTL / playwright / cypress / msw; no test script                                |
| CI / enforcement                             |  0/10 | No workflow, no pre-commit; nothing enforces the tests run                                         |
| Honesty of existing tests (no theater)       |  8/10 | Load-bearing tests assert behavior, not mock choreography — with the exceptions flagged above      |
| Overall shippability as product blueprint    |  3/10 | Fine for a learning codebase; not a shippable-product stance                                       |

## Implications for the PM-DB greenfield project

| # | Recommendation                                             | Detail                                                                                                                                                                                                                                                                                                                                                                             |
| - | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Do NOT repeat NoobBook's approach                          | "No CI, 3% test ratio, zero frontend tests, zero e2e, zero authz tests" is a learning-codebase stance, not a shippable-product stance. A Claude-powered SQL interface into production data needs the inverse: security-critical code TDD'd, integration tests on every PR, e2e covers the PM happy path.                                                                          |
| 2 | TDD the tool executor layer FIRST                          | Greenfield equivalent of `database_executor.py::_validate_readonly_query` + `_quote_identifier` must be written test-first. (a) Adversarial corpus of SQL injection / statement-stacking / comment-based bypass / CTE-recursion-DoS attempts as *spec*, not post-CVE regression. (b) Property-based (Hypothesis) tests for identifier quoting. (c) Round-trip MCP-tool-call → executor → driver → resultset serialization contract. NoobBook shows you what "no tests here" looks like — don't copy. |
| 3 | Contract-test every MCP server you consume                 | Hermetic MCP fixture (in-process stdio server replying canned JSON-RPC) to pin tool listing, invocation, auth header pass-through, failure modes (timeout → user-visible error, not silent empty). NoobBook's `mcp_client.py` has `ALLOWED_STDIO_COMMANDS`, `SHELL_METACHAR_PATTERN`, `BLOCKED_ENV_KEYS` — zero tests. Test those as *executable policy*. [Fowler — contract test; Shore — don't mock code you don't own, use a real subprocess server]. |
| 4 | Playwright for the PM flow                                 | 3-panel workspace (Sources / Chat / Studio) has zero e2e in NoobBook. For a PM-facing product, one Playwright test (login as PM → add DB source → ask question → assert citation tooltip opens) is worth 50 unit tests. `CLAUDE.md` already lists `npx playwright install` as a system dep — never actually used. Don't inherit that dead dependency; install it and use it.      |
| 5 | Pyramid shape to target                                    | ~70% narrow integration (route + service + fake DB + faked LLM responder); ~25% pure unit (parsers, validators, pricers — what NoobBook already does well); ~5% e2e (PM login → query → answer → audit log row). No solitary unit tests against orchestration services — that's where over-mocking hides bugs (cf. `test_deep_research_agent.py`).                                 |
| 6 | Concrete first week                                        | (a) GitHub Actions `pytest` on every PR + block merge on red. (b) Require a test for any new file under `services/auth/` or `services/tool_executors/`. (c) Write SQL-validator adversarial suite *before* writing the validator. (d) Add Playwright with one happy-path test + wire to CI.                                                                                        |
| 7 | Reuse from NoobBook what's actually reusable               | `test_claude_parsing_utils.py` (SDK-shape simulation via `SimpleNamespace` rather than mocking `anthropic`), `test_chunking.py`, `test_citation_utils.py`, `test_text_utils.py`, `test_cost_tracking.py`. Portable patterns. Copy those, drop the rest, write the auth / executor / e2e layer NoobBook lacks.                                                                       |

### Target pyramid (greenfield)

```
              /\
             /E2\        ~ 5%   Playwright: PM login -> query -> answer -> audit log row
            /----\
           /      \
          /   IT   \     ~70%   route + service + fake DB + faked LLM responder
         /----------\
        /            \
       /    UNIT      \  ~25%   parsers, validators, pricers (NoobBook-style pure-fn tests)
      /________________\
```
