from app.agents.runtime import RunLimits, RunRequest, RunResult, RuntimeRunner, ToolCall
from app.agents.runtime.fake import ScriptedProviderAdapter
from app.chat.tools.binding import bind_chat_tools
from app.config.tool import tool_loader


def test_notion_bad_filter_json_returns_runtime_tool_error(monkeypatch):
    def fail_query_database(**kwargs):
        raise AssertionError("Notion client should not be called")

    monkeypatch.setattr(
        "app.connectors.knowledge.notion_client.query_database",
        fail_query_database,
    )

    tools = bind_chat_tools(
        [tool_loader.load_tool_spec("chat_tools", "notion_query_database")],
        project_id="project-1",
        chat_id="chat-1",
        user_id="user-1",
        mcp_registry={},
    )
    provider = ScriptedProviderAdapter(
        [
            RunResult(
                provider="fake",
                model="fake-model",
                status="requires_tools",
                tool_calls=[
                    ToolCall(
                        call_id="call-1",
                        name="notion_query_database",
                        arguments={
                            "database_id": "db-1",
                            "filter_json": "[]",
                        },
                    )
                ],
            ),
            RunResult(provider="fake", model="fake-model", status="complete"),
        ]
    )

    result = RuntimeRunner().run(
        RunRequest(
            provider="fake",
            model="fake-model",
            purpose="chat",
            tools=tools,
            limits=RunLimits(max_tool_turns=1),
        ),
        provider,
    )

    assert result.tool_results[0].is_error is True
    assert "filter_json" in result.tool_results[0].content
    assert "JSON object" in result.tool_results[0].content
