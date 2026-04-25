"""
Chat domain root and public surface.

Charter (NBB-104): Chat loop, streaming, memory invocation, and chat
persistence coordination. Owns the agentic loop, chat/message stores, and
chat-invoked tool adapters exposed to Claude.

Allowed imports:
- `api/` route modules import this package's public surface.
- This package may depend on `auth/`, `projects/`, `sources/`, `connectors/`,
  `background/`, and `providers/` through their published surfaces.
- Other domains may import the chat public surface; they must not reach into
  chat internals.

Public surface (NBB-301):
- `chat.send(project_id, chat_id, message, identity) -> ChatResponse`
- `chat.stream(project_id, chat_id, message, identity) -> Iterator[ChatEvent]`
- `chat.tools` — registry/public-surface scaffolding for chat-owned tool
  schemas. Capability-aware exposure waits for NBB-303.
- `chat.store` — re-exports `ChatStore` and `MessageStore`.
- `chat.schemas` — `ChatResponse`, `ChatEvent`, and chat contract shapes
  traced to NBB-205.

Migration source: `backend/app/services/chat_services/` and
`backend/app/services/tool_executors/` feed this domain; moves are owned by
`NBB-301` through `NBB-304`.
"""
from typing import Iterator, Optional

from app.auth.identity import RequestIdentity
from app.chat import loop, schemas, store, tools
from app.chat.schemas import ChatEvent, ChatResponse


__all__ = [
    "ChatEvent",
    "ChatResponse",
    "schemas",
    "send",
    "store",
    "stream",
    "tools",
]


def send(
    project_id: str,
    chat_id: str,
    message: str,
    identity: Optional[RequestIdentity] = None,
) -> ChatResponse:
    """Run a chat turn synchronously and return the saved message rows.

    Public surface entry point. Internals run through `chat.loop.run_send`,
    which delegates to the legacy `MainChatService` until NBB-302 splits it.
    """
    return loop.run_send(project_id, chat_id, message, identity)


def stream(
    project_id: str,
    chat_id: str,
    message: str,
    identity: Optional[RequestIdentity] = None,
) -> Iterator[ChatEvent]:
    """Run a chat turn and yield streaming events.

    Each yielded item is a `ChatEvent` with `event` from the frozen catalog
    in NBB-205 Contract 1 (`user_message`, `ping`, `assistant_delta`,
    `assistant_done`, `error`) and a contract-shaped `data` payload.
    """
    return loop.run_stream(project_id, chat_id, message, identity)
