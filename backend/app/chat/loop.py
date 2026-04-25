"""
Shared chat agentic loop entry points used by both `chat.send` and
`chat.stream`.

NBB-301 lands this module as the single seam through which the public chat
surface reaches the legacy `MainChatService`. NBB-302 will extract real
loop, context, persistence, tool-policy, and streaming internals here. Do
not split or refactor `main_chat_service.py` from this file — that work is
explicitly deferred to NBB-302.
"""
import logging
import queue
import threading
from typing import Any, Dict, Iterator, Optional

from app.auth.identity import RequestIdentity
from app.chat.schemas import ChatEvent, ChatResponse
from app.services.chat_services import main_chat_service


logger = logging.getLogger(__name__)


# Sentinel posted onto the streaming queue to signal the worker is done.
_STREAM_SENTINEL = object()


def run_send(
    project_id: str,
    chat_id: str,
    message: str,
    identity: Optional[RequestIdentity],
) -> ChatResponse:
    """Run the non-streaming chat flow and return the saved message rows.

    `identity` is captured on the public surface for forward compatibility;
    the legacy `MainChatService.send_message` does not yet accept it. NBB-302
    will plumb it into the split loop.
    """
    user_msg, assistant_msg = main_chat_service.send_message(
        project_id=project_id,
        chat_id=chat_id,
        user_message_text=message,
    )
    return {"user_message": user_msg, "assistant_message": assistant_msg}


def run_stream(
    project_id: str,
    chat_id: str,
    message: str,
    identity: Optional[RequestIdentity],
) -> Iterator[ChatEvent]:
    """Run the streaming chat flow and yield ChatEvent dicts.

    The legacy `MainChatService.stream_message` is callback-driven; this
    function adapts that callback into a generator using a worker thread and
    a sentinel-terminated queue. The thread is daemonized so a dropped
    consumer cannot leak it. The five event names yielded are the frozen
    catalog from NBB-205 Contract 1.
    """
    event_queue: "queue.Queue[object]" = queue.Queue()
    user_id = identity.user_id if identity is not None else None

    def emit(event_name: str, payload: Dict[str, Any]) -> None:
        event_queue.put({"event": event_name, "data": payload or {}})

    def worker() -> None:
        try:
            main_chat_service.stream_message(
                project_id=project_id,
                chat_id=chat_id,
                user_message_text=message,
                user_id=user_id,
                on_event=emit,
            )
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
