from app.chat.store import ChatStore
from app.chat.message.store import MessageStore


def test_chat_store_extracts_text_from_runtime_parts() -> None:
    content = [{"type": "text", "text": "hello"}]

    assert ChatStore._extract_text_content(content) == "hello"
    assert ChatStore._content_has_tool_part(content) is False
    assert ChatStore._derive_message_type("user", content) == "user_input"


def test_chat_store_hides_runtime_tool_intermediates() -> None:
    assistant_content = [
        {"type": "text", "text": "checking"},
        {
            "type": "tool_call",
            "call_id": "toolu_1",
            "name": "search_sources",
            "arguments": {"query": "x"},
        },
    ]
    user_content = [
        {
            "type": "tool_result",
            "call_id": "toolu_1",
            "name": "search_sources",
            "content": "result",
            "is_error": False,
        }
    ]

    assert ChatStore._content_has_tool_part(assistant_content) is True
    assert ChatStore._derive_message_type("assistant", assistant_content) == "tool_call"
    assert ChatStore._derive_message_type("user", user_content) == "tool_result"


def test_message_store_migrates_legacy_anthropic_blocks_to_runtime_parts() -> None:
    store = object.__new__(MessageStore)
    content = [
        {"type": "text", "text": "checking"},
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "search_sources",
            "input": {"query": "contracts"},
        },
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": "encoded",
            },
            "title": "deck.pdf - Page 3",
        },
    ]

    parts = MessageStore._normalize_content_for_storage(store, content)

    assert parts[0] == {"type": "text", "text": "checking"}
    assert parts[1] == {
        "type": "tool_call",
        "call_id": "toolu_1",
        "provider_call_id": "toolu_1",
        "name": "search_sources",
        "arguments": {"query": "contracts"},
    }
    assert parts[2]["type"] == "media"
    assert parts[2]["kind"] == "document"
    assert parts[2]["media_type"] == "application/pdf"
    assert parts[2]["data"] == "encoded"
    assert parts[2]["title"] == "deck.pdf - Page 3"
    assert parts[2]["provider_metadata"]["anthropic"]["type"] == "document"
