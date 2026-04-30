from pathlib import Path
from typing import Any, Optional

import pytest
from pydantic import Field, ValidationError

from app.agents.runtime import (
    ProviderMetadataPart,
    ProviderErrorInfo,
    ProviderRunError,
    RunEvent,
    RunLimits,
    RunMessage,
    RunRequest,
    RunResult,
    RuntimeRunner,
    StructuredResult,
    ToolCall,
    ToolCallPart,
    ToolContext,
    ToolResult,
    ToolResultError,
    LocalToolSpec,
    McpProxyToolSpec,
    Usage,
    require_tool_result_payload,
    tool_result_payloads,
)
from app.agents.runtime.fake import ScriptedProviderAdapter
from app.base.contracts import ContractModel
from app.config.tool import tool_loader
from app.providers.openai.schema import function_schema, strict_model_schema


class AddInput(ContractModel):
    left: int
    right: int
    label: Optional[str] = None


class AddOutput(ContractModel):
    value: int


class MapInput(ContractModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    note: Optional[str] = None


def _add_handler(value: AddInput, context: ToolContext) -> AddOutput:
    return AddOutput(value=value.left + value.right)


def test_strict_schema_requires_all_fields_and_rejects_extra_properties():
    schema = strict_model_schema(AddInput)

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["left", "right", "label"]
    assert schema["properties"]["label"]["anyOf"][1]["type"] == "null"


def test_openai_schema_rejects_freeform_maps():
    with pytest.raises(ValueError, match="free-form object"):
        strict_model_schema(MapInput)


def test_openai_function_schema_rejects_freeform_maps():
    tool = LocalToolSpec(
        name="filter_things",
        description="Filter things.",
        input_model=MapInput,
        output_model=AddOutput,
        handler=None,
    )

    with pytest.raises(ValueError, match="free-form object"):
        function_schema(tool)


def test_openai_function_schema_accepts_strict_mcp_proxy_arguments_json():
    tool = McpProxyToolSpec(
        name="mcp_call",
        description="Call an enabled MCP tool.",
    )

    schema = function_schema(tool)["parameters"]

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["tool_id", "arguments_json"]
    assert schema["properties"]["arguments_json"]["type"] == "string"


def test_openai_schema_compiles_from_same_tool_spec():
    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=_add_handler,
    )

    schema = function_schema(tool)

    assert schema["type"] == "function"
    assert schema["name"] == "add_numbers"
    assert schema["strict"] is True
    assert schema["parameters"]["additionalProperties"] is False


def test_converted_search_tool_preserves_optional_inputs_in_strict_schema():
    tool = tool_loader.load_tool_spec("chat_tools", "source_search_tool")

    schema = function_schema(tool)["parameters"]

    assert set(schema["required"]) == {"source_id", "keywords", "query"}
    assert {"type": "null"} in schema["properties"]["keywords"]["anyOf"]
    assert {"type": "null"} in schema["properties"]["query"]["anyOf"]

    parsed = tool.validate_input({"source_id": "src-1"})
    assert parsed.model_dump(mode="json") == {
        "source_id": "src-1",
        "keywords": None,
        "query": None,
    }


def test_converted_memory_tool_preserves_optional_inputs_in_strict_schema():
    tool = tool_loader.load_tool_spec("chat_tools", "memory_tool")

    schema = function_schema(tool)["parameters"]

    assert set(schema["required"]) == {
        "project_memory",
        "user_memory",
        "why_generated",
    }
    assert {"type": "null"} in schema["properties"]["project_memory"]["anyOf"]
    assert {"type": "null"} in schema["properties"]["user_memory"]["anyOf"]

    parsed = tool.validate_input({"why_generated": "user asked me to remember it"})
    assert parsed.model_dump(mode="json") == {
        "project_memory": None,
        "user_memory": None,
        "why_generated": "user asked me to remember it",
    }


def test_connector_proxy_tools_compile_for_openai_strict_schema():
    mcp_tool = McpProxyToolSpec(
        name="call_mcp_tool",
        description="Call one enabled MCP tool.",
    )
    notion_tool = tool_loader.load_tool_spec("chat_tools", "notion_query_database")

    mcp_schema = function_schema(mcp_tool)["parameters"]
    notion_schema = function_schema(notion_tool)["parameters"]

    assert mcp_schema["additionalProperties"] is False
    assert mcp_schema["properties"]["arguments_json"]["type"] == "string"
    assert notion_schema["additionalProperties"] is False
    assert "filter_json" in notion_schema["required"]
    assert {"type": "null"} in notion_schema["properties"]["filter_json"]["anyOf"]


def test_registered_local_tools_compile_for_openai_strict_schema():
    failures: list[str] = []
    for category in tool_loader.get_available_categories():
        for name in tool_loader.get_available_tools(category):
            tool = tool_loader.load_tool_spec(category, name)
            if tool.kind not in {"local", "mcp_proxy"}:
                continue
            try:
                function_schema(tool)
            except Exception as exc:  # pragma: no cover - assertion reports details
                failures.append(f"{category}/{name}: {exc}")

    assert failures == []


def test_converted_tool_validation_rejects_invalid_optional_types():
    tool = tool_loader.load_tool_spec("chat_tools", "source_search_tool")

    with pytest.raises(ValidationError):
        tool.validate_input({"source_id": "src-1", "keywords": "not-a-list"})


def test_runtime_has_no_json_schema_local_tool_path():
    app_root = Path(__file__).parents[2] / "app"
    forbidden = [
        "tool" + "_from_schema(",
        "input_json" + "_schema",
        "stricten_json" + "_schema",
    ]

    offenders = [
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if any(token in path.read_text() for token in forbidden)
    ]

    assert offenders == []


def test_tool_result_helper_returns_validated_payloads():
    result = RunResult(
        provider="fake",
        model="fake-model",
        tool_calls=[
            ToolCall(
                call_id="call-raw",
                name="add_numbers",
                arguments={"left": 100, "right": 200},
            )
        ],
        tool_results=[
            ToolResult(
                call_id="call-1",
                name="add_numbers",
                content={"value": 5},
            )
        ],
    )

    assert require_tool_result_payload(result, "add_numbers", dict) == {"value": 5}
    assert tool_result_payloads(result, "add_numbers", dict) == [{"value": 5}]


def test_tool_result_helper_rejects_missing_or_error_results():
    raw_only = RunResult(
        provider="fake",
        model="fake-model",
        tool_calls=[
            ToolCall(
                call_id="call-1",
                name="add_numbers",
                arguments={"left": 2, "right": 3},
            )
        ],
    )

    with pytest.raises(ToolResultError, match="did not return"):
        require_tool_result_payload(raw_only, "add_numbers", dict)

    error_result = RunResult(
        provider="fake",
        model="fake-model",
        tool_results=[
            ToolResult(
                call_id="call-1",
                name="add_numbers",
                content="invalid input",
                is_error=True,
            )
        ],
    )

    with pytest.raises(ToolResultError, match="returned an error"):
        require_tool_result_payload(error_result, "add_numbers", dict)


def test_tool_result_helper_rejects_wrong_payload_type():
    result = RunResult(
        provider="fake",
        model="fake-model",
        tool_results=[
            ToolResult(
                call_id="call-1",
                name="add_numbers",
                content="not a dict",
            )
        ],
    )

    with pytest.raises(ToolResultError, match="expected dict"):
        require_tool_result_payload(result, "add_numbers", dict)


def test_runtime_executes_typed_tool_loop_with_fake_provider():
    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=_add_handler,
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
                        name="add_numbers",
                        arguments={"left": 2, "right": 3},
                    )
                ],
            ),
            RunResult(
                provider="fake",
                model="fake-model",
                status="complete",
                text="The result is 5.",
            ),
        ]
    )
    request = RunRequest(
        provider="fake",
        model="fake-model",
        purpose="test",
        messages=[
            RunMessage(
                role="user",
                content=[{"type": "text", "text": "add 2 and 3"}],
            )
        ],
        tools=[tool],
        limits=RunLimits(max_tool_turns=2),
    )

    result = RuntimeRunner().run(request, provider)

    assert result.text == "The result is 5."
    assert result.tool_results[0].content == {"value": 5}
    assert len(provider.requests) == 2
    assert provider.requests[1].messages[-1].role == "tool"


def test_runtime_preserves_provider_continuation_parts_between_tool_turns():
    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=_add_handler,
    )
    reasoning = ProviderMetadataPart(
        provider="openai",
        values={"type": "reasoning", "id": "rs_1", "summary": []},
    )
    call_part = ToolCallPart(
        call_id="call-1",
        provider_call_id="call-1",
        name="add_numbers",
        arguments={"left": 2, "right": 3},
    )
    provider = ScriptedProviderAdapter(
        [
            RunResult(
                provider="fake",
                model="fake-model",
                status="requires_tools",
                content=[reasoning, call_part],
                tool_calls=[
                    ToolCall(
                        call_id="call-1",
                        provider_call_id="call-1",
                        name="add_numbers",
                        arguments={"left": 2, "right": 3},
                    )
                ],
            ),
            RunResult(provider="fake", model="fake-model", status="complete"),
        ]
    )

    RuntimeRunner().run(
        RunRequest(
            provider="fake",
            model="fake-model",
            purpose="test",
            tools=[tool],
            limits=RunLimits(max_tool_turns=2),
        ),
        provider,
    )

    assistant_message = provider.requests[1].messages[-2]
    assert assistant_message.content[0] == reasoning
    assert assistant_message.content[1] == call_part


def test_runtime_returns_whole_run_usage_and_request_ids():
    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=_add_handler,
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
                        name="add_numbers",
                        arguments={"left": 2, "right": 3},
                    )
                ],
                usage=Usage(input_tokens=10, output_tokens=2),
                provider_request_ids=["req-1"],
            ),
            RunResult(
                provider="fake",
                model="fake-model",
                status="complete",
                usage=Usage(input_tokens=4, output_tokens=7),
                provider_request_ids=["req-2"],
            ),
        ]
    )

    result = RuntimeRunner().run(
        RunRequest(
            provider="fake",
            model="fake-model",
            purpose="test",
            tools=[tool],
            limits=RunLimits(max_tool_turns=2),
        ),
        provider,
    )

    assert result.usage.input_tokens == 14
    assert result.usage.output_tokens == 9
    assert result.provider_request_ids == ["req-1", "req-2"]


def test_provider_error_after_tool_turn_keeps_failed_run_transcript():
    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=_add_handler,
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
                        name="add_numbers",
                        arguments={"left": 2, "right": 3},
                    )
                ],
                usage=Usage(input_tokens=10, output_tokens=2),
                provider_request_ids=["req-1"],
            ),
            RunResult(
                provider="fake",
                model="fake-model",
                status="error",
                error="provider failed",
                error_info=ProviderErrorInfo(
                    provider="fake",
                    model="fake-model",
                    kind="server",
                    message="provider failed",
                    retryable=True,
                ),
                usage=Usage(input_tokens=4, output_tokens=1),
                provider_request_ids=["req-2"],
            ),
        ]
    )

    with pytest.raises(ProviderRunError) as exc_info:
        RuntimeRunner().run(
            RunRequest(
                provider="fake",
                model="fake-model",
                purpose="test",
                tools=[tool],
                limits=RunLimits(max_tool_turns=2),
            ),
            provider,
        )

    failed = exc_info.value.result
    assert failed is not None
    assert failed.error_info is not None
    assert failed.error_info.kind == "server"
    assert failed.tool_results[0].content == {"value": 5}
    assert failed.generated_messages[0].role == "assistant"
    assert failed.generated_messages[1].role == "tool"
    assert failed.provider_request_ids == ["req-1", "req-2"]
    assert failed.usage.input_tokens == 14


def test_invalid_tool_input_is_rejected_before_handler_execution():
    calls = {"count": 0}

    def handler(value: AddInput, context: ToolContext) -> AddOutput:
        calls["count"] += 1
        return AddOutput(value=value.left + value.right)

    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=handler,
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
                        name="add_numbers",
                        arguments={"left": "not-an-int", "right": 3},
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
            purpose="test",
            tools=[tool],
        ),
        provider,
    )

    assert calls["count"] == 0
    assert result.tool_results[0].is_error is True
    assert "Invalid tool input" in result.tool_results[0].content


def test_falsy_non_object_tool_input_is_rejected_before_handler_execution():
    calls = {"count": 0}

    def handler(value: AddInput, context: ToolContext) -> AddOutput:
        calls["count"] += 1
        return AddOutput(value=value.left + value.right)

    tool = LocalToolSpec(
        name="add_numbers",
        description="Add two numbers.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=handler,
    )
    with pytest.raises(ValidationError):
        tool.execute([], ToolContext())

    assert calls["count"] == 0


def test_runtime_stops_after_successful_terminating_tool():
    tool = LocalToolSpec(
        name="finish",
        description="Finish the run.",
        input_model=AddInput,
        output_model=AddOutput,
        handler=_add_handler,
        terminates_run=True,
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
                        name="finish",
                        arguments={"left": 2, "right": 3},
                    )
                ],
                usage=Usage(input_tokens=4, output_tokens=2),
                provider_request_ids=["req-1"],
            ),
            RunResult(
                provider="fake",
                model="fake-model",
                status="complete",
                text="should not be called",
            ),
        ]
    )

    result = RuntimeRunner().run(
        RunRequest(
            provider="fake",
            model="fake-model",
            purpose="test",
            tools=[tool],
            limits=RunLimits(max_tool_turns=2),
        ),
        provider,
    )

    assert result.status == "complete"
    assert result.tool_results[0].content == {"value": 5}
    assert result.usage.input_tokens == 4
    assert result.provider_request_ids == ["req-1"]
    assert len(provider.requests) == 1
    assert result.events[-1].data["terminated_by_tools"] == ["finish"]


def test_structured_result_states_are_explicit():
    assert StructuredResult(status="parsed", parsed={"ok": True}).parsed == {"ok": True}
    assert StructuredResult(status="refusal", refusal="No.").refusal == "No."
    assert StructuredResult(status="invalid", error="bad json").error == "bad json"


def test_fake_provider_streams_normalized_events():
    provider = ScriptedProviderAdapter(
        [],
        stream_events=[
            RunEvent(type="text_delta", data={"delta": "hel"}),
            RunEvent(type="text_delta", data={"delta": "lo"}),
            RunEvent(type="final", data={"text": "hello"}),
        ],
    )

    events = list(
        provider.stream_turn(
            RunRequest(provider="fake", model="fake-model", purpose="stream-test")
        )
    )

    assert [event.type for event in events] == ["text_delta", "text_delta", "final"]
    assert "".join(event.data.get("delta", "") for event in events) == "hello"
