import sys
from types import SimpleNamespace

from app.agents.runtime import RunLimits, RunRequest, RunResult, RuntimeRunner, ToolCall
from app.agents.runtime.fake import ScriptedProviderAdapter
from app.agents.runtime.tool import McpProxyToolSpec
from app.connectors.mcp.tools import (
    MCP_PROXY_TOOL_NAME,
    McpToolService,
    parse_mcp_arguments_json,
)


def test_mcp_tools_expose_one_proxy_with_external_registry(monkeypatch):
    class FakeStore:
        def get_tool_enabled_connections(self, user_id: str):
            assert user_id == "user-1"
            return [
                {
                    "id": "conn-1",
                    "name": "Demo MCP",
                    "cached_tools": [
                        {
                            "name": "search",
                            "description": "Search records",
                            "input_schema": {
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                                "required": ["query"],
                            },
                        }
                    ],
                }
            ]

    monkeypatch.setitem(
        sys.modules,
        "app.connectors.mcp.store",
        SimpleNamespace(mcp_connection_service=FakeStore()),
    )

    tools, registry = McpToolService().get_available_tools(user_id="user-1")

    assert len(tools) == 1
    assert isinstance(tools[0], McpProxyToolSpec)
    assert tools[0].name == MCP_PROXY_TOOL_NAME
    assert set(registry) == {"mcp_demo_mcp_search"}
    assert registry["mcp_demo_mcp_search"]["tool_name"] == "search"


def test_mcp_proxy_validates_external_arguments_before_execution(monkeypatch):
    registry = {
        "mcp_demo_search": {
            "connection_id": "conn-1",
            "tool_name": "search",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    }

    result = McpToolService().execute(
        tool_id="mcp_demo_search",
        arguments={"query": 123},
        registry=registry,
    )

    assert result.startswith("Error: Invalid MCP arguments")


def test_mcp_proxy_rejects_non_object_arguments_json():
    arguments, error = parse_mcp_arguments_json('["bad"]')

    assert arguments == {}
    assert error == "Error: arguments_json must decode to a JSON object"


def test_mcp_proxy_invalid_arguments_json_returns_runtime_tool_error(monkeypatch):
    class FakeStore:
        def get_tool_enabled_connections(self, user_id: str):
            assert user_id == "user-1"
            return [
                {
                    "id": "conn-1",
                    "name": "Demo MCP",
                    "cached_tools": [
                        {
                            "name": "search",
                            "description": "Search records",
                            "input_schema": {
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                                "required": ["query"],
                            },
                        }
                    ],
                }
            ]

    monkeypatch.setitem(
        sys.modules,
        "app.connectors.mcp.store",
        SimpleNamespace(mcp_connection_service=FakeStore()),
    )
    tools, registry = McpToolService().get_available_tools(user_id="user-1")
    provider = ScriptedProviderAdapter(
        [
            RunResult(
                provider="fake",
                model="fake-model",
                status="requires_tools",
                tool_calls=[
                    ToolCall(
                        call_id="call-1",
                        name=MCP_PROXY_TOOL_NAME,
                        arguments={
                            "tool_id": "mcp_demo_mcp_search",
                            "arguments_json": "[]",
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
            user_id="user-1",
            tools=tools,
            limits=RunLimits(max_tool_turns=1),
            metadata={"mcp_registry": registry},
        ),
        provider,
    )

    assert result.tool_results[0].is_error is True
    assert "JSON object" in result.tool_results[0].content


def test_mcp_proxy_executes_allowed_tool(monkeypatch):
    class FakeStore:
        def get_connection(self, **kwargs):
            assert kwargs["connection_id"] == "conn-1"
            assert kwargs["include_secret"] is True
            return {
                "name": "Demo MCP",
                "server_url": "https://example.test/mcp",
                "auth_type": "none",
                "transport": "sse",
            }

    calls = {}

    def fake_call_tool(**kwargs):
        calls.update(kwargs)
        return "ok"

    monkeypatch.setitem(
        sys.modules,
        "app.connectors.mcp.store",
        SimpleNamespace(mcp_connection_service=FakeStore()),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.providers.mcp.client",
        SimpleNamespace(call_tool=fake_call_tool),
    )

    result = McpToolService().execute(
        tool_id="mcp_demo_search",
        arguments={"query": "status"},
        registry={
            "mcp_demo_search": {
                "connection_id": "conn-1",
                "tool_name": "search",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        },
    )

    assert result == "ok"
    assert calls["tool_name"] == "search"
    assert calls["arguments"] == {"query": "status"}
