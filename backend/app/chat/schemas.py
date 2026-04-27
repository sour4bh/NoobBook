"""
Chat contract shapes re-exported on the chat public surface.

Trace: docs/contracts/README.md (NBB-205) — Contract 1 (chat streaming event
format), Contract 2 (citation marker/lookup), Contract 3 (chat tool
invocation/result), Contract 9 (`messages.content` JSONB shape). The names
below preserve current production wire shape; redesign is deferred to D-005.
"""
from typing import Any, Dict, Tuple, TypedDict

from app.chat.contracts import (
    ChatMessageResponse,
    ChatStreamEvent,
    MessageContent,
)


# Frozen catalog of chat streaming event names per NBB-205 Contract 1.
# Adding a new event kind requires a DEFERRED.md entry and a paired
# frontend change in the same merge.
CHAT_EVENT_NAMES: Tuple[str, ...] = (
    "user_message",
    "ping",
    "assistant_delta",
    "assistant_done",
    "error",
)


class ChatResponse(TypedDict):
    """Non-streaming chat response shape.

    Mirrors the JSON body of `POST /api/v1/projects/<id>/chats/<id>/messages`
    minus the transport `success` envelope. Each message is a stored row
    whose `content` is JSONB blocks per NBB-205 Contract 9.
    """

    user_message: Dict[str, Any]
    assistant_message: Dict[str, Any]


class ChatEvent(TypedDict):
    """One streaming event yielded from `chat.stream`.

    `event` is one of CHAT_EVENT_NAMES. `data` is the per-event payload as
    documented in NBB-205 Contract 1 (e.g. `{"delta": "..."}` for
    `assistant_delta`, the stored message row for `user_message` /
    `assistant_done`, `{"message": str, "assistant_message"?: dict}` for
    `error`, and `{}` for `ping`).
    """

    event: str
    data: Dict[str, Any]
