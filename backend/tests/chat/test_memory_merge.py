from typing import Any, Dict, Optional
from app.agents.runtime import RunResult, ToolResult, Usage
from app.agents.runtime.tool import EmptyInput, LocalToolSpec
from app.chat.memory import merge
from app.chat.memory.run import MemoryExecutor
from app.config.prompt import RenderedPrompt


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
    sent_request: Dict[str, Any] = {}

    monkeypatch.setattr(merge, "_tool_def", None)
    monkeypatch.setattr(merge, "project_service", fake_project_service)

    def render_prompt(prompt_name: str, context=None, **kwargs) -> RenderedPrompt:
        assert prompt_name == "memory"
        assert context == {
            "memory_type": "user",
            "current_memory": "prefers concise answers",
            "new_memory": "works mostly in Python",
            "reason": "chat stated preference",
        }
        return RenderedPrompt(
            name="memory",
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            max_tokens=200,
            temperature=0,
            system_prompt="merge memory",
            user_message="user|prefers concise answers|works mostly in Python|chat stated preference",
        )

    monkeypatch.setattr(merge, "render_prompt", render_prompt)

    def load_tool_spec(category: str, tool_name: str):
        loaded_tools.append((category, tool_name))
        return LocalToolSpec(
            name="save_memory",
            description="Save memory",
            input_model=EmptyInput,
            metadata={"registry_name": tool_name},
        )

    def run_with_provider(request) -> RunResult:
        sent_request["request"] = request
        return RunResult(
            provider="anthropic",
            model="claude-3-5-haiku-latest",
            status="complete",
            tool_results=[
                ToolResult(
                    call_id="toolu_memory",
                    name="save_memory",
                    content={"memory": "prefers concise Python answers"},
                )
            ],
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    monkeypatch.setattr(merge.tool_loader, "load_tool_spec", load_tool_spec)
    monkeypatch.setattr(merge, "run_with_provider", run_with_provider)

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
    request = sent_request["request"]
    assert request.tool_choice.type == "tool"
    assert request.tool_choice.name == "save_memory"
    assert request.project_id is None
    assert request.user_id == "user-1"


def test_memory_executor_passes_project_context_to_user_memory_merge(monkeypatch) -> None:
    captured: Dict[str, Any] = {}

    def update_memory(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr("app.chat.memory.run.merge.update_memory", update_memory)

    MemoryExecutor()._update_user_memory(
        project_id="project-1",
        new_memory="likes concise answers",
        reason="chat stated preference",
        user_id="user-1",
    )

    assert captured == {
        "memory_type": "user",
        "new_memory": "likes concise answers",
        "reason": "chat stated preference",
        "project_id": "project-1",
        "user_id": "user-1",
    }
