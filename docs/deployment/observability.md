# Observability and Deployment Boundaries

Owner: `NBB-208B`. Scope is documentation and inventory only; this file does not grant permission to change runtime behavior. Runtime config ownership is `NBB-208A`; provider/connector ownership lives in `backend/app/providers/CHARTER.md` and `backend/app/connectors/CHARTER.md`; background lifecycle is `NBB-210` under `backend/app/background/`.

This inventory names the owner for each observability concern, calls out what local tests cannot prove, and records the deployment constraints that migration work must preserve.

## What lives where

### Cross-cutting (no domain owner)

| Concern | File | Notes |
|---|---|---|
| Root logger setup | `backend/app/utils/logger.py` (`setup_logging`) | Called once from `create_app`. Streams to stdout with `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`. Quiets `urllib3`, `werkzeug`, `httpcore`, `httpx`, `hpack`, `PIL`. |
| Log level env | `LOG_LEVEL` (Flask config) and `GUNICORN_LOG_LEVEL` (Gunicorn only) | Flask uses `LOG_LEVEL`; Gunicorn access/error logs use `GUNICORN_LOG_LEVEL` (default `info`). |
| Module logger convention | `logging.getLogger(__name__)` at module top | Every service follows this pattern. No custom handler/formatter installed per-module. |
| Gunicorn access/error log | `backend/gunicorn.conf.py` | `accesslog = "-"` (stdout), `errorlog = "-"` (stderr). No trace header injection. |
| nginx access log | `frontend/nginx.conf` | Uses nginx image defaults. Not configured in the repo; the deploy image controls format. |

### Providers (third-party call observability)

| Concern | File | Notes |
|---|---|---|
| Opik wrapping of Anthropic client | `backend/app/services/integrations/claude/claude_service.py` (`_get_client`, `_build_opik_kwargs`, `_run_tracked`) | Owned by `providers/` per `backend/app/providers/CHARTER.md`. `track_anthropic` wraps the client when `OPIK_API_KEY` is set; `@opik.track` adds a parent trace with `project_id`, `user_id`, `thread_id`, `tags` metadata. Graceful no-op when the key or package is absent. |
| Opik env knobs | `OPIK_API_KEY`, `OPIK_URL_OVERRIDE`, `OPIK_WORKSPACE`, `OPIK_PROJECT_NAME` | Documented in `backend/app/api/settings/api_keys.py`. Reload hook: `claude_service.reload_config()` (added in `NBB-208A`). |
| Opik key validator | `backend/app/services/app_settings/validation/opik_validator.py` | Attempts `opik.configure(api_key=...)`. Remaining three OPIK\_\* keys are accepted-if-present. |
| Spending-limit short-circuit log | `backend/app/utils/cost_tracking.py` via `claude_service.send_message` | Raises before the API call; the warning path for missing `project_id` is emitted here, not in domain code. |

### Background (task lifecycle)

| Concern | File | Notes |
|---|---|---|
| Task lifecycle log | `backend/app/services/background_services/task_service.py` (`logger.info` on submit/start/complete; `logger.exception` on failure) | Owned by `background/` per `backend/app/background/CHARTER.md`. Persistent truth lives in the Supabase `background_tasks` table; the in-process logger is for operator visibility only. |
| Worker pool | `ThreadPoolExecutor(max_workers=MAX_WORKERS)` inside `TaskService` | See "Async paths" below for the trace-context gap. |
| Per-domain background threads | `backend/app/services/tool_executors/memory_executor.py` (memory merge), `backend/app/services/integrations/freshdesk/freshdesk_sync_service.py` (`freshdesk-global-sync` daemon thread), `backend/app/services/ai_services/pdf_service.py` and `.../pptx_service.py` (page/slide `ThreadPoolExecutor`) | These are domain-owned today. Logging inside each thread goes through the domain's module logger. None currently propagate request identity or a trace ID across the thread boundary. |
| Stale-task cleanup | `TaskService._cleanup_stale_tasks_on_startup` | Logs a count of stale tasks marked failed at startup. |

### Chat

| Concern | File | Notes |
|---|---|---|
| SSE streaming | `backend/app/api/messages/routes.py` (`stream_message`) | Spawns a `threading.Thread` that runs `main_chat_service.stream_message` and pushes SSE events into a `queue.Queue`. Errors are emitted as `error` events and logged via `app.logger.error`. Response headers set `X-Accel-Buffering: no` to bypass nginx buffering. |
| Non-streaming path | `backend/app/api/chats/routes.py`, `.../messages/routes.py` | Uses `current_app.logger.error` / `.exception` for route-level failures. |
| Socket.IO registration | `backend/app/__init__.py` (`socketio.init_app(app, async_mode=_async_mode)`) | `_async_mode` switches on `FLASK_ENV=production` (gevent) vs anything else (threading). Chat streaming uses SSE rather than Socket.IO events today; Socket.IO is wired but under-used by chat. |

### Sources and Studio

| Concern | File | Notes |
|---|---|---|
| Per-service logger | Every `backend/app/services/**/*.py` module | Uses `logging.getLogger(__name__)`. No domain-specific observability hooks beyond the cross-cutting stdlib logger. |
| Source pipeline progress | Persisted to `sources.status` + `background_tasks.progress` rows | RLS and persistence owned by `NBB-204`; lifecycle owned by `NBB-210`. Not a separate observability channel. |
| Studio generation logs | `backend/app/services/studio_services/*` (e.g., `flash_cards_service.py`) | Same stdlib pattern; no per-domain hook. |
| Web-agent execution debug dumps | `data/projects/{id}/agents/web_agent/{execution_id}.json` | Local file artifact only (frozen under `STRUCTURE.md`). Not a deployable observability channel. |

### Deployment surface (no Python package owner)

| File | Role |
|---|---|
| `backend/gunicorn.conf.py` | Binds `0.0.0.0:$PORT` (default 5001), one `GeventWebSocketWorker`, `timeout=300`, `graceful_timeout=30`, `keepalive=5`, `max_requests=5000` with `max_requests_jitter=200`, `accesslog/errorlog` to stdout/stderr. |
| `frontend/nginx.conf` | Serves the Vite SPA bundle, proxies `/api/` to `noobbook-backend:5001`, streams `/api/v1/projects/*/chats/*/messages/stream` with `proxy_buffering off` + `X-Accel-Buffering: no`, upgrades `/socket.io/` for WebSocket with `proxy_read_timeout 86400s`, allows 100 MB uploads. |
| `backend/entrypoint.sh` | Seeds `data/prompts/` from the baked staging dir, then chooses `gunicorn -c gunicorn.conf.py run:app` when `FLASK_ENV=production`, else `python run.py` (Werkzeug). |
| `docker/` | Self-hosted Supabase stack plus backend/frontend images. See `docker/MAC_SETUP.md`. Not in the backend Python write scope. |

## Owner split for future migrations

| Class of concern | Owning ticket/root | Action |
|---|---|---|
| Cross-cutting logger bootstrap | `backend/app/utils/logger.py` under the cross-cutting utility family | Reviewed by each utility drain (`NBB-705A` through `NBB-705E`). No domain move. |
| Opik wrapping, provider trace metadata | `providers/` per `backend/app/providers/CHARTER.md` | Stays attached to `ClaudeService`. `reload_config()` already symmetrical with other providers after `NBB-208A`. |
| Background task logs | `background/` per `backend/app/background/CHARTER.md` | Moves under `NBB-210`. The polymorphic-RLS constraint documented in the charter governs what gets logged (never log cross-tenant ids). |
| Chat SSE event formatting | `chat/` public surface (`NBB-301`/`NBB-302`) | The SSE envelope (`_format_sse`, worker thread, sentinel) moves with chat streaming. The route adapter stays under `backend/app/api/`. |
| Domain service logs | The domain root receiving each service | Each `NBB-209A`–`E`, `NBB-402`, `NBB-503`, etc. carries its `logging.getLogger(__name__)` call sites with it. No central registry is needed. |

## Deployment constraints migration must preserve

These are the invariants encoded in `backend/gunicorn.conf.py`, `frontend/nginx.conf`, `backend/entrypoint.sh`, and `backend/app/__init__.py`. Changing any of them is out of scope for `NBB-208B` and for any normal migration ticket. They are listed so movement tickets do not trip over them by accident.

1. **Single Gunicorn worker.** Flask-SocketIO requires exactly one worker without a Redis message queue. `workers = 1` must remain until a message queue lands. Adding workers silently breaks Socket.IO fan-out.
2. **GeventWebSocketWorker class.** `worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"` monkey-patches the stdlib inside `init_process` — after fork, before the app loads. `preload_app` must remain unset. Do not monkey-patch in app code.
3. **Async mode switches on `FLASK_ENV`.** `backend/app/__init__.py` picks `'gevent'` when `FLASK_ENV=production`, else `'threading'`. Local tests run against the threading mode; gevent-specific behavior is not proved by the suite.
4. **Gunicorn `timeout=300` pairs with nginx `proxy_read_timeout 300s`.** The API-proxy read timeout and worker timeout must stay aligned or long Claude tool loops get killed mid-request.
5. **SSE passthrough requires nginx `proxy_buffering off` + `X-Accel-Buffering: no`.** Both the location block for `.../messages/stream` and the Flask response headers set this. Removing either buffers the stream and breaks token-by-token display.
6. **Socket.IO upgrade headers.** The `/socket.io/` block sets `Upgrade`/`Connection: upgrade` and `proxy_read_timeout 86400s`. WebSocket idle timeout is load-bearing; standard 60s read timeouts disconnect live voice sessions.
7. **`max_requests = 5000` drops active SSE/WebSocket streams when it trips.** With `workers=1` and gevent, a worker recycle kills every in-flight long-lived connection. Keep the threshold high enough that idle-reload is the dominant cause of recycling.
8. **`client_max_body_size 100M`.** Upload ceiling for PDFs, PPTX, and audio sources. Any stricter nginx frontend will return 413 before the backend sees the request.
9. **Opik attachment must stay lazy.** `claude_service._get_client` wraps the client on first use. Eager attachment would fail imports when `OPIK_API_KEY` is unset and no test covers the eager path. The `try/except ImportError` guard must stay.
10. **`entrypoint.sh` reseeds `data/prompts/`.** Prompt JSON is container-baked; the volume is rewritten on every start. Prompt-ownership migrations (`NBB-207B`) must keep the staging-dir contract intact.

## Behavior local tests cannot prove

The ticket body requires naming behavior that local tests cannot cover. These are documentation-only claims until a deployment smoke test exists.

- **gevent monkey-patching.** Runs inside `GeventWebSocketWorker.init_process()`. Tests run under pytest without Gunicorn, so the monkey-patched stdlib is never exercised.
- **`preload_app = False` required.** Setting `preload_app = True` would monkey-patch the master before fork and break signal handling. Unit tests do not exercise fork semantics.
- **Flask-SocketIO single-worker assumption.** Tests run one Flask instance; concurrent multi-worker misrouting (events landing on the wrong worker without a Redis queue) cannot be reproduced locally.
- **nginx SSE passthrough.** The test client returns the SSE generator directly; no test proves nginx does not buffer it.
- **nginx Socket.IO upgrade headers.** No test drives nginx.
- **Gunicorn `timeout=300` / `max_requests=5000` recycling.** No test reproduces a worker recycle or a hang beyond 300 s.
- **Opik end-to-end trace upload.** `_opik_enabled` branches are covered indirectly by unit mocks; the real `track_anthropic` + background batching is not exercised.
- **Production `_async_mode = 'gevent'`.** Tests default to `FLASK_ENV != production`, so the threading branch is the one under test coverage.
- **Thread-boundary log context.** Each `ThreadPoolExecutor`/`threading.Thread` (`task_service`, `memory_executor`, `pdf_service`, `pptx_service`, `freshdesk_sync_service`, the SSE worker in `messages/routes.py`) inherits the root logger but does **not** propagate request identity, `project_id`, or any `trace_id`. There is no `trace_id`/`correlation_id`/`request_id` infrastructure in the codebase today (confirmed by full-tree grep). Opik traces carry `project_id`/`user_id`/`chat_id` via `_build_opik_kwargs`, but only at the Claude-client boundary; they are not available to arbitrary logs inside background threads. Adding cross-thread trace context is a future ticket, not an `NBB-208B` deliverable.
- **CORS preflight behavior.** `enforce_auth` short-circuits on `OPTIONS`. Browser-driven preflight is covered at contract level only; the actual `Access-Control-Allow-*` values are shaped by `CORS_ALLOWED_ORIGINS` in runtime config.

## Pointers

- Runtime config bootstrap: `backend/app/__init__.py` (the `NBB-208A` docstring enumerates every bootstrap step).
- Provider observability: `backend/app/providers/CHARTER.md`.
- Background lifecycle: `backend/app/background/CHARTER.md`.
- API-key validator ↔ reload-hook map: `backend/app/api/settings/api_keys.py` module header.
- Gunicorn settings: `backend/gunicorn.conf.py`.
- nginx serving/streaming: `frontend/nginx.conf`.
- Container entrypoint: `backend/entrypoint.sh`.
- Docker stack: `docker/` and `docker/MAC_SETUP.md`.
