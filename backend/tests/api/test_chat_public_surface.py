"""
Smoke tests for the chat public surface introduced in NBB-301.

The ticket's two acceptance criteria covered here:
1. `from app.chat import send, stream, tools, store, memory, schemas` resolves and
   exposes the committed names.
2. The `chats` and `messages` blueprints still register route rules that call
   `chat.send`/`chat.stream` instead of legacy internals.
"""
from app.chat.schemas import CHAT_EVENT_NAMES


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
    """Acceptance #2: route rule remains registered after switching to chat.send."""
    rules = {rule.rule for rule in blueprint_client.application.url_map.iter_rules()}
    assert "/api/v1/projects/<project_id>/chats/<chat_id>/messages" in rules


def test_messages_stream_route_still_guards_unauthenticated_callers(blueprint_client):
    """Streaming route rule remains registered after switching to chat.stream."""
    rules = {rule.rule for rule in blueprint_client.application.url_map.iter_rules()}
    assert "/api/v1/projects/<project_id>/chats/<chat_id>/messages/stream" in rules
