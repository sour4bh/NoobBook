import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.agents.runtime import (
    MediaPart,
    ProviderMetadataPart,
    RunLimits,
    RunEvent,
    RunMessage,
    RunRequest,
    RunResult,
    TextPart,
    ToolCallPart,
    ToolContext,
    ToolResultPart,
    LocalToolSpec,
    get_provider_adapter,
    run_with_provider,
    stream_with_provider,
)
from app.agents.runtime.error import ProviderRunError
from app.agents.runtime.fake import ScriptedProviderAdapter
from app.config.model import resolve_model_selection_for_project
from app.providers.anthropic.adapter import AnthropicMessagesAdapter
from app.providers.openai.adapter import OpenAIResponsesAdapter


class SearchInput(BaseModel):
    query: str


class SearchOutput(BaseModel):
    result: str


def _tool() -> LocalToolSpec:
    def handler(args: SearchInput, context: ToolContext) -> SearchOutput:
        return SearchOutput(result=f"found {args.query}")

    return LocalToolSpec(
        name="search_sources",
        description="Search sources",
        input_model=SearchInput,
        output_model=SearchOutput,
        handler=handler,
    )


def test_provider_selector_accepts_injected_adapters() -> None:
    provider = ScriptedProviderAdapter([])

    assert get_provider_adapter("fake", {"fake": provider}) is provider


def test_same_tool_spec_compiles_for_anthropic_and_openai() -> None:
    tool = _tool()
    anthropic = AnthropicMessagesAdapter(service=SimpleNamespace())
    openai = OpenAIResponsesAdapter(client=SimpleNamespace())

    anthropic_schema = anthropic.compile_tools([tool])[0]
    openai_schema = openai.compile_tools([tool])[0]

    assert anthropic_schema["name"] == openai_schema["name"] == "search_sources"
    assert anthropic_schema["input_schema"]["properties"]["query"]["type"] == "string"
    assert openai_schema["type"] == "function"
    assert openai_schema["parameters"]["additionalProperties"] is False
    assert openai_schema["strict"] is True


def test_openai_can_run_local_tool_loop_through_provider_selector() -> None:
    calls = {"count": 0}
    captured_inputs: list[list[dict]] = []

    class Responses:
        def create(self, **kwargs):
            calls["count"] += 1
            captured_inputs.append(kwargs["input"])
            if calls["count"] == 1:
                return SimpleNamespace(
                    id="resp_tool",
                    model="gpt-5.1",
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            call_id="call_1",
                            name="search_sources",
                            arguments=json.dumps({"query": "workspace roles"}),
                        )
                    ],
                    usage=SimpleNamespace(input_tokens=8, output_tokens=3),
                )
            return SimpleNamespace(
                id="resp_final",
                model="gpt-5.1",
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text="found workspace roles",
                            )
                        ],
                    )
                ],
                usage=SimpleNamespace(input_tokens=4, output_tokens=4),
            )

    adapter = OpenAIResponsesAdapter(
        client=SimpleNamespace(responses=Responses()),
    )
    request = RunRequest(
        provider="openai",
        model="gpt-5.1",
        purpose="chat",
        messages=[RunMessage(role="user", content=[TextPart(text="search")])],
        tools=[_tool()],
        limits=RunLimits(max_tool_turns=2, max_output_tokens=64),
    )

    result = run_with_provider(request, {"openai": adapter})

    assert result.text == "found workspace roles"
    assert result.tool_results[0].content == {"result": "found workspace roles"}
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 7
    assert captured_inputs[1][-1]["type"] == "function_call_output"
    assert captured_inputs[1][-1]["call_id"] == "call_1"


def test_openai_reasoning_items_are_replayed_with_tool_outputs() -> None:
    calls = {"count": 0}
    captured_inputs: list[list[dict]] = []

    class Responses:
        def create(self, **kwargs):
            calls["count"] += 1
            captured_inputs.append(kwargs["input"])
            if calls["count"] == 1:
                return SimpleNamespace(
                    id="resp_tool",
                    model="gpt-5.1",
                    output=[
                        {"type": "reasoning", "id": "rs_1", "summary": []},
                        SimpleNamespace(
                            type="function_call",
                            call_id="call_1",
                            name="search_sources",
                            arguments=json.dumps({"query": "workspace roles"}),
                        ),
                    ],
                    usage=SimpleNamespace(input_tokens=8, output_tokens=3),
                )
            return SimpleNamespace(
                id="resp_final",
                model="gpt-5.1",
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(type="output_text", text="done"),
                        ],
                    )
                ],
                usage=SimpleNamespace(input_tokens=4, output_tokens=4),
            )

    adapter = OpenAIResponsesAdapter(
        client=SimpleNamespace(responses=Responses()),
    )

    run_with_provider(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="chat",
            messages=[RunMessage(role="user", content=[TextPart(text="search")])],
            tools=[_tool()],
            limits=RunLimits(max_tool_turns=2, max_output_tokens=64),
        ),
        {"openai": adapter},
    )

    second_input = captured_inputs[1]
    assert {"type": "reasoning", "id": "rs_1", "summary": []} in second_input
    assert second_input[-1]["type"] == "function_call_output"


def test_run_request_routes_openai_selection_to_openai_adapter(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    provider = ScriptedProviderAdapter(
        [RunResult(provider="openai", model="gpt-5.1", status="complete", text="ok")]
    )
    selection = resolve_model_selection_for_project("gpt-5.1", None)

    result = run_with_provider(
        RunRequest(
            provider=selection.provider,
            model=selection.model,
            purpose="test",
            messages=[RunMessage(role="user", content=[TextPart(text="hello")])],
            limits=RunLimits(max_output_tokens=32, temperature=0),
        ),
        {"openai": provider},
    )

    assert result.text == "ok"
    assert provider.requests[0].provider == "openai"
    assert provider.requests[0].model == "gpt-5.1"


def test_stream_request_routes_openai_selection_to_streaming_adapter(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    provider = ScriptedProviderAdapter(
        [],
        stream_events=[
            RunEvent(type="text_delta", data={"delta": "he"}),
            RunEvent(type="text_delta", data={"delta": "llo"}),
            RunEvent(type="usage", data={"input_tokens": 2, "output_tokens": 1}),
            RunEvent(type="final", data={"text": "hello", "status": "complete"}),
        ],
    )
    selection = resolve_model_selection_for_project("gpt-5.1", None)
    deltas: list[str] = []

    result = stream_with_provider(
        RunRequest(
            provider=selection.provider,
            model=selection.model,
            purpose="test",
            messages=[RunMessage(role="user", content=[TextPart(text="hello")])],
            limits=RunLimits(max_output_tokens=32, temperature=0),
        ),
        {"openai": provider},
        on_text_delta=deltas.append,
    )

    assert deltas == ["he", "llo"]
    assert result.text == "hello"
    assert result.usage.input_tokens == 2
    assert provider.requests[0].provider == "openai"
    assert provider.requests[0].model == "gpt-5.1"


def test_stream_runtime_raises_openai_terminal_failure(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    class Responses:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            return iter(
                [
                    {"type": "response.output_text.delta", "delta": "partial"},
                    {
                        "type": "response.incomplete",
                        "response": {
                            "id": "resp_incomplete",
                            "model": "gpt-5.1",
                            "status": "incomplete",
                            "incomplete_details": {"reason": "max_output_tokens"},
                            "output": [],
                            "usage": {"input_tokens": 3, "output_tokens": 1},
                        },
                    },
                ]
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))
    deltas: list[str] = []

    with pytest.raises(ProviderRunError) as exc_info:
        stream_with_provider(
            RunRequest(
                provider="openai",
                model="gpt-5.1",
                purpose="test",
                messages=[RunMessage(role="user", content=[TextPart(text="hello")])],
                limits=RunLimits(max_output_tokens=32, temperature=0),
            ),
            {"openai": adapter},
            on_text_delta=deltas.append,
        )

    assert deltas == ["partial"]
    assert str(exc_info.value) == "OpenAI response incomplete: max_output_tokens"
    assert exc_info.value.partial_text == "partial"
    assert exc_info.value.provider_request_ids == ["resp_incomplete"]


def test_stream_runtime_keeps_openai_reasoning_before_tool_outputs(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    class Responses:
        def create(self, **kwargs):
            assert kwargs["stream"] is True
            assert kwargs["include"] == ["reasoning.encrypted_content"]
            return iter(
                [
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": "fc_1",
                        "call_id": "call_1",
                        "name": "search_sources",
                        "arguments": '{"query":"workspace roles"}',
                    },
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_tool",
                            "model": "gpt-5.1",
                            "output": [
                                {
                                    "type": "reasoning",
                                    "id": "rs_1",
                                    "summary": [],
                                    "encrypted_content": "enc",
                                },
                                {
                                    "type": "function_call",
                                    "call_id": "call_1",
                                    "name": "search_sources",
                                    "arguments": '{"query":"workspace roles"}',
                                },
                            ],
                            "usage": {"input_tokens": 8, "output_tokens": 3},
                        },
                    },
                ]
            )

    adapter = OpenAIResponsesAdapter(client=SimpleNamespace(responses=Responses()))
    terminating_tool = _tool().model_copy(update={"terminates_run": True})

    result = stream_with_provider(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="chat",
            messages=[RunMessage(role="user", content=[TextPart(text="search")])],
            limits=RunLimits(max_output_tokens=64, temperature=0),
            tools=[terminating_tool],
        ),
        {"openai": adapter},
    )

    assert isinstance(result.content[0], ProviderMetadataPart)
    assert result.content[0].provider == "openai"
    assert result.content[0].values == {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [],
        "encrypted_content": "enc",
    }
    assert isinstance(result.content[1], ToolCallPart)
    assert result.content[1].call_id == "call_1"

    stored_content = [part.model_dump(mode="json") for part in result.content]
    assert stored_content[0]["type"] == "provider_metadata"
    assert stored_content[1]["type"] == "tool_call"

    replay_items = adapter._input_items(
        RunRequest(
            provider="openai",
            model="gpt-5.1",
            purpose="chat",
            messages=[
                RunMessage(role="assistant", content=result.content),
                RunMessage(
                    role="tool",
                    content=[
                        ToolResultPart(
                            call_id="call_1",
                            name="search_sources",
                            content={"result": "ok"},
                        )
                    ],
                ),
            ],
        )
    )

    assert replay_items[0] == {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [],
        "encrypted_content": "enc",
    }
    assert replay_items[1]["type"] == "function_call"
    assert replay_items[1]["call_id"] == "call_1"
    assert replay_items[2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"result": "ok"}',
    }


def test_runtime_request_keeps_media_parts_provider_neutral() -> None:
    provider = ScriptedProviderAdapter(
        [RunResult(provider="fake", model="fake-model", status="complete", text="ok")]
    )

    run_with_provider(
        RunRequest(
            provider="fake",
            model="fake-model",
            purpose="media",
            messages=[
                RunMessage(
                    role="user",
                    content=[
                        TextPart(text="extract"),
                        MediaPart(
                            kind="document",
                            media_type="application/pdf",
                            data="pdf123",
                            filename="source.pdf",
                        ),
                    ],
                )
            ],
            limits=RunLimits(max_output_tokens=32, temperature=0),
        ),
        {"fake": provider},
    )

    media = provider.requests[0].messages[0].content[1]
    assert isinstance(media, MediaPart)
    assert media.kind == "document"
    assert media.media_type == "application/pdf"
    assert media.data == "pdf123"


def test_run_request_keeps_runtime_history_provider_neutral() -> None:
    provider = ScriptedProviderAdapter(
        [RunResult(provider="fake", model="fake-model", status="complete", text="ok")]
    )
    assistant_content = [
        ProviderMetadataPart(
            provider="openai",
            values={
                "type": "reasoning",
                "id": "rs_1",
                "summary": [],
                "encrypted_content": "enc",
            },
        ),
        ToolCallPart(
            call_id="call_1",
            provider_call_id="call_1",
            name="search_sources",
            arguments={"query": "workspace roles"},
        ),
    ]

    run_with_provider(
        RunRequest(
            provider="fake",
            model="fake-model",
            purpose="chat",
            messages=[
                RunMessage(role="user", content=[TextPart(text="search")]),
                RunMessage(role="assistant", content=assistant_content),
                RunMessage(
                    role="tool",
                    content=[
                        ToolResultPart(
                            call_id="call_1",
                            name="search_sources",
                            content='{"result": "ok"}',
                            is_error=False,
                        )
                    ],
                ),
            ],
            limits=RunLimits(max_output_tokens=32, temperature=0),
        ),
        {"fake": provider},
    )

    replayed = provider.requests[0].messages
    assert replayed[1].content[0] == ProviderMetadataPart(
        provider="openai",
        values={
            "type": "reasoning",
            "id": "rs_1",
            "summary": [],
            "encrypted_content": "enc",
        },
    )
    assert isinstance(replayed[1].content[1], ToolCallPart)
    assert replayed[2].role == "tool"
    assert isinstance(replayed[2].content[0], ToolResultPart)
    assert replayed[2].content[0].call_id == "call_1"
