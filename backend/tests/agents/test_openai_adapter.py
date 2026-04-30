import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel

from app.agents.runtime.contract import (
    MediaPart,
    ProviderMetadataPart,
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    ToolCallPart,
    ToolResultPart,
)
from app.agents.runtime.tool import LocalToolSpec, ToolContext, provider_tool
from app.providers.openai.adapter import OpenAIResponsesAdapter


class SearchInput(BaseModel):
    query: str


class SearchOutput(BaseModel):
    result: str


def _tool() -> LocalToolSpec:
    def handler(args: SearchInput, context: ToolContext) -> SearchOutput:
        return SearchOutput(result=args.query)

    return LocalToolSpec(
        name="search_sources",
        description="Search sources",
        input_model=SearchInput,
        output_model=SearchOutput,
        handler=handler,
    )


def _openai_response(status_code: int = 429) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return httpx.Response(
        status_code,
        request=request,
        headers={"x-request-id": f"req-{status_code}"},
        json={"error": {"type": "provider_type", "code": "provider_code"}},
    )


def test_openai_adapter_compiles_strict_function_schema() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())

    schema = adapter.compile_tools([_tool()])[0]

    assert schema["type"] == "function"
    assert schema["name"] == "search_sources"
    assert schema["strict"] is True
    assert schema["parameters"]["additionalProperties"] is False
    assert schema["parameters"]["required"] == ["query"]


def test_openai_adapter_rejects_anthropic_hosted_tools() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())
    tool = provider_tool(
        registry_name="web_search",
        name="web_search",
        provider_type="web_search_20250305",
    )

    try:
        adapter.compile_tools([tool])
    except ValueError as exc:
        assert "has no OpenAI schema" in str(exc)
    else:
        raise AssertionError("Expected unsupported hosted tool to fail closed")


def test_openai_adapter_normalizes_function_call_response() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())
    response = SimpleNamespace(
        id="resp_1",
        model="gpt-5.1",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="search_sources",
                arguments=json.dumps({"query": "revenue"}),
            )
        ],
        usage=SimpleNamespace(input_tokens=11, output_tokens=3),
    )

    result = adapter.normalize_response(response, model_fallback="gpt-5.1")

    assert result.status == "requires_tools"
    assert result.tool_calls[0].call_id == "call_1"
    assert result.tool_calls[0].arguments == {"query": "revenue"}
    assert result.usage.input_tokens == 11
    assert result.provider_request_ids == ["resp_1"]


def test_openai_adapter_sends_function_call_outputs() -> None:
    captures = {}

    class Responses:
        def create(self, **kwargs):
            captures.update(kwargs)
            return SimpleNamespace(
                id="resp_2",
                model="gpt-5.1",
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(type="output_text", text="done"),
                        ],
                    )
                ],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    client = SimpleNamespace(responses=Responses())
    adapter = OpenAIResponsesAdapter(client=client)
    request = RunRequest(
        provider="openai",
        model="gpt-5.1",
        purpose="test",
        messages=[
            RunMessage(role="user", content=[TextPart(text="hi")]),
            RunMessage(
                role="assistant",
                content=[
                    ToolCallPart(
                        call_id="call_1",
                        name="search_sources",
                        arguments={"query": "x"},
                    )
                ],
            ),
            RunMessage(
                role="tool",
                content=[
                    ToolResultPart(
                        call_id="call_1",
                        name="search_sources",
                        content={"result": "x"},
                    )
                ],
            ),
        ],
        limits=RunLimits(max_output_tokens=32, temperature=0),
    )

    result = adapter.run_turn(request)

    assert result.text == "done"
    assert captures["input"][1]["type"] == "function_call"
    assert captures["input"][2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"result": "x"}',
    }
    assert captures["store"] is False
    assert captures["include"] == ["reasoning.encrypted_content"]


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (
            openai.RateLimitError(
                "rate limited",
                response=_openai_response(429),
                body={"error": {"type": "rate_limit_error", "code": "rate_limit"}},
            ),
            "rate_limit",
            True,
        ),
        (
            openai.APIConnectionError(
                message="connection failed",
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            ),
            "connection",
            True,
        ),
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            ),
            "timeout",
            True,
        ),
        (
            openai.AuthenticationError(
                "bad key",
                response=_openai_response(401),
                body={"error": {"type": "invalid_api_key", "code": "bad_key"}},
            ),
            "authentication",
            False,
        ),
        (
            openai.PermissionDeniedError(
                "forbidden",
                response=_openai_response(403),
                body={"error": {"type": "permission_denied", "code": "forbidden"}},
            ),
            "permission",
            False,
        ),
        (
            openai.BadRequestError(
                "bad request",
                response=_openai_response(400),
                body={"error": {"type": "invalid_request_error", "code": "bad"}},
            ),
            "bad_request",
            False,
        ),
        (
            openai.InternalServerError(
                "server failed",
                response=_openai_response(500),
                body={"error": {"type": "server_error", "code": "server"}},
            ),
            "server",
            True,
        ),
    ],
)
def test_openai_adapter_maps_sdk_errors_to_runtime_error_info(
    exc: Exception,
    kind: str,
    retryable: bool,
) -> None:
    class Responses:
        def create(self, **kwargs):
            raise exc

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    result = adapter.run_turn(
        RunRequest(provider="openai", model="gpt-5.1", purpose="test")
    )

    assert result.status == "error"
    assert result.error_info is not None
    assert result.error_info.kind == kind
    assert result.error_info.retryable is retryable
    assert result.events[0].data["error_info"]["kind"] == kind


def test_openai_adapter_streams_sdk_exception_as_error_result() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")

    class Responses:
        def create(self, **kwargs):
            def stream():
                yield {"type": "response.output_text.delta", "delta": "partial"}
                raise openai.APITimeoutError(request=request)

            return stream()

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    events = list(
        adapter.stream_turn(RunRequest(provider="openai", model="gpt-5.1", purpose="test"))
    )

    assert [event.type for event in events] == ["text_delta", "error", "final"]
    assert events[1].data["error_info"]["kind"] == "timeout"
    assert events[-1].data["result"]["status"] == "error"
    assert events[-1].data["result"]["error_info"]["kind"] == "timeout"


def test_openai_adapter_keeps_system_messages_out_of_input_items() -> None:
    captures = {}

    class Responses:
        def create(self, **kwargs):
            captures.update(kwargs)
            return SimpleNamespace(id="resp_system", model="gpt-5.1", output=[], usage={})

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    adapter.run_turn(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="test",
            system_prompt="base",
            messages=[
                RunMessage(role="system", content=[TextPart(text="extra")]),
                RunMessage(role="user", content=[TextPart(text="hello")]),
            ],
        )
    )

    assert captures["instructions"] == "base\n\nextra"
    assert captures["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "hello"}]}
    ]


def test_openai_adapter_translates_anthropic_tool_choice_metadata() -> None:
    captures = {}

    class Responses:
        def create(self, **kwargs):
            captures.update(kwargs)
            return SimpleNamespace(
                id="resp_2",
                model="gpt-5.1",
                output=[],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    adapter.run_turn(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="test",
            tools=[_tool()],
            metadata={"tool_choice": {"type": "tool", "name": "search_sources"}},
        )
    )

    assert captures["tool_choice"] == {"type": "function", "name": "search_sources"}


def test_openai_adapter_rejects_missing_named_tool_choice_before_sdk_call() -> None:
    class Responses:
        def create(self, **kwargs):
            raise AssertionError("OpenAI SDK should not be called")

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    try:
        adapter.run_turn(
            RunRequest(
                provider="openai",
                model="gpt-5.1",
                purpose="test",
                tools=[_tool()],
                tool_choice=ToolChoice(type="tool", name="missing_tool"),
            )
        )
    except ValueError as exc:
        assert "missing_tool" in str(exc)
    else:
        raise AssertionError("Expected missing named tool choice to fail")


def test_openai_adapter_serializes_runtime_media_parts() -> None:
    captures = {}

    class Responses:
        def create(self, **kwargs):
            captures.update(kwargs)
            return SimpleNamespace(id="resp_media", model="gpt-5.1", output=[], usage={})

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    adapter.run_turn(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="vision",
            messages=[
                RunMessage(
                    role="user",
                    content=[
                        TextPart(text="extract this"),
                        MediaPart(
                            kind="image",
                            media_type="image/png",
                            data="abc123",
                        ),
                        MediaPart(
                            kind="document",
                            media_type="application/pdf",
                            data="pdf123",
                            filename="source.pdf",
                        ),
                    ],
                )
            ],
        )
    )

    content = captures["input"][0]["content"]
    assert content == [
        {"type": "input_text", "text": "extract this"},
        {
            "type": "input_image",
            "detail": "auto",
            "image_url": "data:image/png;base64,abc123",
        },
        {
            "type": "input_file",
            "filename": "source.pdf",
            "file_data": "pdf123",
        },
    ]


def test_openai_adapter_represents_refusals_as_structured_result() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())
    response = {
        "id": "resp_refusal",
        "model": "gpt-5.1",
        "output": [
            {
                "type": "message",
                "content": [{"type": "refusal", "refusal": "cannot comply"}],
            }
        ],
        "usage": {"input_tokens": 2, "output_tokens": 1},
    }

    result = adapter.normalize_response(response, model_fallback="gpt-5.1")

    assert result.structured is not None
    assert result.structured.status == "refusal"
    assert result.structured.refusal == "cannot comply"
    assert result.text == "cannot comply"
    assert result.content == [TextPart(text="cannot comply")]


def test_openai_adapter_sends_pydantic_structured_output_format() -> None:
    captures = {}

    class Responses:
        def create(self, **kwargs):
            captures.update(kwargs)
            return SimpleNamespace(
                id="resp_structured",
                model="gpt-5.1",
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text='{"result": "done"}',
                            )
                        ],
                    )
                ],
                usage={},
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))
    result = adapter.run_turn(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="structured",
            output_model=SearchOutput,
        )
    )

    assert captures["text"]["format"]["type"] == "json_schema"
    assert captures["text"]["format"]["strict"] is True
    assert result.structured is not None
    assert result.structured.status == "parsed"
    assert result.structured.parsed == {"result": "done"}


def test_openai_adapter_normalizes_usage_details() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())

    result = adapter.normalize_response(
        {
            "id": "resp_usage",
            "model": "gpt-5.1",
            "output": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 25,
                "input_tokens_details": {"cached_tokens": 40},
                "output_tokens_details": {"reasoning_tokens": 9},
            },
        },
        model_fallback="gpt-5.1",
    )

    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 25
    assert result.usage.cache_read_input_tokens == 40
    assert result.usage.provider_units == {
        "cached_tokens": 40,
        "reasoning_tokens": 9,
    }


def test_openai_adapter_surfaces_failed_response_status() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())

    result = adapter.normalize_response(
        SimpleNamespace(
            id="resp_failed",
            model="gpt-5.1",
            status="failed",
            error=SimpleNamespace(message="quota exceeded"),
            output=[],
            usage=SimpleNamespace(input_tokens=2, output_tokens=0),
        ),
        model_fallback="gpt-5.1",
    )

    assert result.status == "error"
    assert result.error == "quota exceeded"
    assert result.usage.input_tokens == 2
    assert result.provider_state is not None
    assert result.provider_state.values["status"] == "failed"
    assert result.events[-1].type == "final"
    assert result.error_info is not None
    assert result.error_info.kind == "rate_limit"
    assert result.events[-1].data["status"] == "error"
    assert result.events[-1].data["error"] == "quota exceeded"
    assert result.events[-1].data["error_info"]["kind"] == "rate_limit"


def test_openai_adapter_surfaces_incomplete_response_status() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())

    result = adapter.normalize_response(
        {
            "id": "resp_incomplete",
            "model": "gpt-5.1",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [],
            "usage": {"input_tokens": 2, "output_tokens": 1},
        },
        model_fallback="gpt-5.1",
    )

    assert result.status == "error"
    assert result.error == "OpenAI response incomplete: max_output_tokens"
    assert result.error_info is not None
    assert result.error_info.kind == "incomplete"
    assert result.provider_state is not None
    assert result.provider_state.values["status"] == "incomplete"


def test_openai_adapter_streams_text_delta_and_final_events() -> None:
    class Responses:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return iter(
                [
                    {"type": "response.output_text.delta", "delta": "he"},
                    {"type": "response.output_text.delta", "delta": "llo"},
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_stream",
                            "model": "gpt-5.1",
                            "output": [
                                {
                                    "type": "message",
                                    "content": [{"type": "output_text", "text": "hello"}],
                                }
                            ],
                            "usage": {"input_tokens": 1, "output_tokens": 1},
                        },
                    },
                ]
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))
    request = RunRequest(provider="openai", model="gpt-5.1", purpose="test")

    events = list(adapter.stream_turn(request))

    assert [event.data.get("delta") for event in events[:2]] == ["he", "llo"]
    assert events[-1].type == "final"
    assert events[-1].data["text"] == "hello"


def test_openai_adapter_streams_failed_terminal_response_as_error() -> None:
    class Responses:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return iter(
                [
                    {"type": "response.output_text.delta", "delta": "partial"},
                    {
                        "type": "response.failed",
                        "response": {
                            "id": "resp_failed",
                            "model": "gpt-5.1",
                            "status": "failed",
                            "error": {"message": "quota exceeded"},
                            "output": [],
                            "usage": {"input_tokens": 4, "output_tokens": 0},
                        },
                    },
                ]
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    events = list(
        adapter.stream_turn(RunRequest(provider="openai", model="gpt-5.1", purpose="test"))
    )

    assert [event.type for event in events] == [
        "text_delta",
        "error",
        "usage",
        "final",
    ]
    assert events[1].data["message"] == "quota exceeded"
    assert events[-1].data["status"] == "error"
    assert events[-1].data["error"] == "quota exceeded"
    assert events[-1].data["result"]["status"] == "error"


def test_openai_adapter_streams_function_call_arguments() -> None:
    class Responses:
        def create(self, **kwargs):
            return iter(
                [
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": "fc_1",
                        "delta": '{"query"',
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": "fc_1",
                        "delta": ':"x"}',
                    },
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": "fc_1",
                        "call_id": "call_1",
                        "name": "search_sources",
                    },
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_tool",
                            "model": "gpt-5.1",
                            "output": [
                                {
                                    "type": "function_call",
                                    "call_id": "call_1",
                                    "name": "search_sources",
                                    "arguments": '{"query":"x"}',
                                }
                            ],
                            "usage": {"input_tokens": 1, "output_tokens": 1},
                        },
                    },
                ]
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    events = list(
        adapter.stream_turn(RunRequest(provider="openai", model="gpt-5.1", purpose="test"))
    )

    assert [event.type for event in events] == ["tool_call", "usage", "final"]
    assert events[0].data == {
        "call_id": "call_1",
        "name": "search_sources",
        "arguments": '{"query":"x"}',
    }
    assert events[-1].data["status"] == "requires_tools"


def test_openai_adapter_streams_function_name_from_output_item_added() -> None:
    class Responses:
        def create(self, **kwargs):
            return iter(
                [
                    {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {
                            "type": "function_call",
                            "id": "fc_1",
                            "call_id": "call_1",
                            "name": "search_sources",
                        },
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": "fc_1",
                        "delta": '{"query":"x"}',
                    },
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": "fc_1",
                    },
                ]
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))

    events = list(
        adapter.stream_turn(RunRequest(provider="openai", model="gpt-5.1", purpose="test"))
    )

    assert events[0].data == {
        "call_id": "call_1",
        "name": "search_sources",
        "arguments": '{"query":"x"}',
    }


def test_openai_adapter_replays_reasoning_metadata_items() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())
    request = RunRequest(
        provider="openai",
        model="gpt-5.1",
        purpose="test",
        messages=[
            RunMessage(
                role="assistant",
                content=[
                    ProviderMetadataPart(
                        provider="openai",
                        values={
                            "type": "reasoning",
                            "id": "rs_1",
                            "summary": [],
                            "encrypted_content": "enc",
                        },
                    )
                ],
            )
        ],
    )

    assert adapter._input_items(request) == [
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [],
            "encrypted_content": "enc",
        }
    ]


def test_openai_adapter_does_not_replay_refusal_metadata_items() -> None:
    adapter = OpenAIResponsesAdapter(client=SimpleNamespace())
    request = RunRequest(
        provider="openai",
        model="gpt-5.1",
        purpose="test",
        messages=[
            RunMessage(
                role="assistant",
                content=[
                    ProviderMetadataPart(
                        provider="openai",
                        values={"type": "refusal", "text": "cannot comply"},
                    )
                ],
            )
        ],
    )

    assert adapter._input_items(request) == []
