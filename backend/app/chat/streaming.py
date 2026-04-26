"""
Streaming mechanics for the chat loop.

Owns three things:

1. `ClaudeStreamError` — wraps a streaming exception with whatever text
   already streamed so the loop can fall back to a partial-text error
   message.
2. `call_claude(...)` — single seam over `claude_service.send_message` /
   `stream_message` so the agentic loop in `chat.loop` does not branch
   on streaming-vs-non-streaming.
3. `iter_chat_events(...)` — converts the loop's callback-driven event
   emission into an SSE-friendly generator using a worker thread and a
   sentinel-terminated queue. The five event names yielded are the
   frozen catalog from NBB-205 Contract 1.
"""
import logging
import queue
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from app.providers.anthropic.response_parser import extract_text
from app.providers.anthropic import claude_service


logger = logging.getLogger(__name__)


# Sentinel posted onto the streaming queue to signal the worker is done.
_STREAM_SENTINEL = object()


class ClaudeStreamError(Exception):
    """Wrap a streaming error with any text that already streamed."""

    def __init__(self, message: str, partial_text: str = ""):
        super().__init__(message)
        self.partial_text = partial_text


def call_claude(
    *,
    stream_text: bool,
    on_text_delta: Optional[Callable[[str], None]] = None,
    **kwargs: Any,
) -> Tuple[Dict[str, Any], str]:
    """Call Claude once, optionally streaming text deltas.

    Non-streaming path bubbles the underlying exception verbatim; the
    streaming path wraps it in `ClaudeStreamError` together with any
    partial text that already reached the consumer, so the loop can
    surface a graceful error message after partial output.
    """
    if not stream_text:
        response = claude_service.send_message(**kwargs)
        return response, extract_text(response)

    streamed_parts: List[str] = []

    def handle_delta(delta: str) -> None:
        streamed_parts.append(delta)
        if on_text_delta:
            on_text_delta(delta)

    try:
        response = claude_service.stream_message(
            on_text_delta=handle_delta,
            **kwargs,
        )
    except Exception as exc:
        partial_text = "".join(streamed_parts)
        raise ClaudeStreamError(str(exc), partial_text) from exc

    return response, "".join(streamed_parts)


def iter_chat_events(
    runner: Callable[[Callable[[str, Dict[str, Any]], None]], None],
) -> Iterator[Dict[str, Any]]:
    """Run a callback-driven chat flow on a worker thread and yield events.

    `runner(emit)` is the inner callable that does the streaming work and
    fires `emit(name, payload)` at the contract points. Errors raised by
    `runner` are converted into a final `error` event so the SSE consumer
    always sees a terminal frame. The worker thread is daemonized so a
    dropped consumer cannot leak it.
    """
    event_queue: "queue.Queue[object]" = queue.Queue()

    def emit(event_name: str, payload: Dict[str, Any]) -> None:
        event_queue.put({"event": event_name, "data": payload or {}})

    def worker() -> None:
        try:
            runner(emit)
        except ValueError as exc:
            emit("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001 — surface to the SSE consumer
            logger.error("Error streaming message: %s", exc, exc_info=True)
            emit("error", {"message": str(exc)})
        finally:
            event_queue.put(_STREAM_SENTINEL)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        item = event_queue.get()
        if item is _STREAM_SENTINEL:
            break
        yield item  # type: ignore[misc]
