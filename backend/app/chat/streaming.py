"""
Streaming mechanics for the chat loop.

Owns `iter_chat_events(...)`, which converts the loop's callback-driven event
emission into an SSE-friendly generator using a worker thread and a
sentinel-terminated queue. The five event names yielded are the frozen catalog
from NBB-205 Contract 1.
"""
import logging
import queue
import threading
from typing import Any, Callable, Dict, Iterator


logger = logging.getLogger(__name__)


# Sentinel posted onto the streaming queue to signal the worker is done.
_STREAM_SENTINEL = object()


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
