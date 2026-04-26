from typing import Any, Dict, Optional

from app.chat.memory import merge


class FakeProjectService:
    def __init__(self) -> None:
        self.saved_user_memory: Optional[str] = None

    def get_user_memory(self, user_id: Optional[str] = None) -> str:
        assert user_id == "user-1"
        return "prefers concise answers"

    def update_user_memory(self, memory: str, user_id: Optional[str] = None) -> bool:
        assert user_id == "user-1"
        self.saved_user_memory = memory
        return True


def test_update_user_memory_forces_save_memory_tool(monkeypatch) -> None:
    fake_project_service = FakeProjectService()
    loaded_tools = []
    sent_messages: Dict[str, Any] = {}

    monkeypatch.setattr(merge, "_prompt_config", None)
    monkeypatch.setattr(merge, "_tool_def", None)
    monkeypatch.setattr(merge, "project_service", fake_project_service)
    monkeypatch.setattr(
        merge.prompt_loader,
        "get_prompt_config",
        lambda prompt_name: {
            "system_prompt": "merge memory",
            "model": "claude-3-5-haiku-latest",
            "max_tokens": 200,
            "temperature": 0,
            "user_message": "{memory_type}|{current_memory}|{new_memory}|{reason}",
        },
    )

    def load_tool(category: str, tool_name: str) -> Dict[str, Any]:
        loaded_tools.append((category, tool_name))
        return {
            "name": "save_memory",
            "description": "Save memory",
            "input_schema": {"type": "object", "properties": {}},
        }

    def send_message(**kwargs) -> Dict[str, Any]:
        sent_messages.update(kwargs)
        return {
            "content_blocks": [],
            "model": "claude-3-5-haiku-latest",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

    monkeypatch.setattr(merge.tool_loader, "load_tool", load_tool)
    monkeypatch.setattr(merge.claude_service, "send_message", send_message)
    monkeypatch.setattr(
        merge.response_parser,
        "extract_tool_inputs",
        lambda response, tool_name: [{"memory": "prefers concise Python answers"}],
    )

    result = merge.update_memory(
        memory_type="user",
        new_memory="works mostly in Python",
        reason="chat stated preference",
        user_id="user-1",
    )

    assert result["success"] is True
    assert result["memory"] == "prefers concise Python answers"
    assert fake_project_service.saved_user_memory == "prefers concise Python answers"
    assert loaded_tools == [("memory_tools", "manage_memory_tool")]
    assert sent_messages["tool_choice"] == {"type": "tool", "name": "save_memory"}
    assert sent_messages["project_id"] is None
