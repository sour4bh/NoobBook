"""
Smoke tests for the chat public surface introduced in NBB-301.

The ticket's two acceptance criteria covered here:
1. `from app.chat import send, stream, tools, store, memory, schemas` resolves and
   exposes the committed names.
2. The `chats` and `messages` blueprints still register and reach their
   401 guard (route file calls `chat.send`/`chat.stream` instead of legacy
   internals without breaking transport).
"""
from app.chat.schemas import CHAT_EVENT_NAMES


PROJECT_ID = "00000000-0000-0000-0000-000000000000"
CHAT_ID = "00000000-0000-0000-0000-000000000001"


def test_chat_public_surface_exports():
    """Spec-required imports must resolve and bind to the right things."""
    from app import chat
    from app.chat import memory, schemas, store, tools  # noqa: F401
    from app.chat import send, stream  # noqa: F401

    assert callable(chat.send), "chat.send must be callable"
    assert callable(chat.stream), "chat.stream must be callable"
    assert chat.tools is tools, "chat.tools attribute must be the tools module"
    assert chat.store is store, "chat.store attribute must be the store module"
    assert chat.memory is memory, "chat.memory attribute must be the memory module"
    assert chat.schemas is schemas, "chat.schemas attribute must be the schemas module"


def test_chat_store_reexports_both_persistence_classes():
    """`chat.store` must re-export ChatStore and MessageStore per spec."""
    from app.chat.store import ChatStore, MessageStore

    assert ChatStore.__name__ == "ChatStore"
    assert MessageStore.__name__ == "MessageStore"


def test_chat_event_catalog_is_frozen():
    """Five event names from NBB-205 Contract 1; adding a sixth is a contract change."""
    assert CHAT_EVENT_NAMES == (
        "user_message",
        "ping",
        "assistant_delta",
        "assistant_done",
        "error",
    )


def test_chat_tools_registry_lists_chat_owned_names():
    """`chat.tools` exposes the chat_tools JSON inventory (NBB-207C)."""
    from app.chat import tools

    assert "source_search_tool" in tools.CHAT_TOOL_NAMES
    assert "memory_tool" in tools.CHAT_TOOL_NAMES
    assert "studio_signal_tool" in tools.CHAT_TOOL_NAMES
    assert callable(tools.get_tool)


def test_messages_route_still_guards_unauthenticated_callers(blueprint_client):
    """Acceptance #2: route reaches its 401 guard after switching to chat.send.

    A 404 here would mean the route module failed to import (which would
    happen if the chat public surface was wired wrong).
    """
    response = blueprint_client.post(
        f"/api/v1/projects/{PROJECT_ID}/chats/{CHAT_ID}/messages",
        json={"message": "hi"},
    )
    assert response.status_code == 401, response.status_code


def test_messages_stream_route_still_guards_unauthenticated_callers(blueprint_client):
    """Streaming route mirrors the same guard contract after the rewire."""
    response = blueprint_client.post(
        f"/api/v1/projects/{PROJECT_ID}/chats/{CHAT_ID}/messages/stream",
        json={"message": "hi"},
    )
    assert response.status_code == 401, response.status_code
