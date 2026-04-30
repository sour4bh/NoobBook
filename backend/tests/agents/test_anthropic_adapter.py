from threading import Event

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from app.agents.runtime import (
    MediaPart,
    RunLimits,
    RunMessage,
    RunRequest,
    ToolChoice,
    ToolCallPart,
    ToolResultPart,
    LocalToolSpec,
)
from app.agents.runtime.tool import provider_tool
from app.providers.anthropic.adapter import AnthropicMessagesAdapter


class StructuredOutput(BaseModel):
    value: str


class SearchInput(BaseModel):
    query: str


class FakeClaudeService:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def send_message(self, **kwargs):
        self.last_kwargs = kwargs
        return self.response

    def stream_message(self, **kwargs):
        self.last_kwargs = kwargs
        on_text_delta = kwargs.get("on_text_delta")
        if on_text_delta:
            on_text_delta("hel")
            on_text_delta("lo")
        return self.response

    def count_tokens(self, messages, **kwargs):
        return len(messages[0]["content"].split())


class BlockingStreamClaudeService(FakeClaudeService):
    def __init__(self, response):
        super().__init__(response)
        self.release = Event()
        self.returned = Event()

    def stream_message(self, **kwargs):
        self.last_kwargs = kwargs
        on_text_delta = kwargs.get("on_text_delta")
        if on_text_delta:
            on_text_delta("hel")
        self.release.wait(timeout=1)
        self.returned.set()
        if on_text_delta:
            on_text_delta("lo")
        return self.response


def _anthropic_response(status_code: int = 429) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(
        status_code,
        request=request,
        headers={"request-id": f"req-{status_code}"},
        json={"error": {"type": "provider_type", "code": "provider_code"}},
    )


def test_anthropic_adapter_compiles_local_and_provider_tools():
    adapter = AnthropicMessagesAdapter(service=FakeClaudeService({}))
    local = LocalToolSpec(name="local_tool", description="Local tool.")
    hosted = provider_tool(
        registry_name="web_search",
        name="web_search",
        provider_type="web_search_20250305",
        metadata={"max_uses": 2},
    )

    schemas = adapter.compile_tools([local, hosted])

    assert schemas[0]["name"] == "local_tool"
    assert schemas[0]["input_schema"]["type"] == "object"
    assert schemas[1] == {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 2,
    }


def test_anthropic_adapter_normalizes_tool_use_response():
    service = FakeClaudeService(
        {
            "content_blocks": [
                {"type": "text", "text": "I'll search."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "search_sources",
                    "input": {"query": "contracts"},
                },
            ],
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "stop_reason": "tool_use",
        }
    )
    adapter = AnthropicMessagesAdapter(service=service)

    result = adapter.run_turn(
        RunRequest(
            provider="anthropic",
            model="claude-sonnet-4-6",
            purpose="chat",
            system_prompt="Use sources.",
            messages=[
                RunMessage(
                    role="user",
                    content=[{"type": "text", "text": "find contracts"}],
                )
            ],
            limits=RunLimits(max_output_tokens=100, temperature=0),
        )
    )

    assert service.last_kwargs["messages"] == [
        {"role": "user", "content": "find contracts"}
    ]
    assert service.last_kwargs["system_prompt"] == "Use sources."
    assert result.status == "requires_tools"
    assert result.text == "I'll search."
    assert result.tool_calls[0].provider_call_id == "toolu_1"
    assert result.tool_calls[0].arguments == {"query": "contracts"}
    assert result.usage.input_tokens == 10


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (
            anthropic.RateLimitError(
                "rate limited",
                response=_anthropic_response(429),
                body={"error": {"type": "rate_limit_error", "code": "rate_limit"}},
            ),
            "rate_limit",
            True,
        ),
        (
            anthropic.APIConnectionError(
                message="connection failed",
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            ),
            "connection",
            True,
        ),
        (
            anthropic.APITimeoutError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            ),
            "timeout",
            True,
        ),
        (
            anthropic.AuthenticationError(
                "bad key",
                response=_anthropic_response(401),
                body={"error": {"type": "authentication_error", "code": "bad_key"}},
            ),
            "authentication",
            False,
        ),
        (
            anthropic.PermissionDeniedError(
                "forbidden",
                response=_anthropic_response(403),
                body={"error": {"type": "permission_error", "code": "forbidden"}},
            ),
            "permission",
            False,
        ),
        (
            anthropic.BadRequestError(
                "bad request",
                response=_anthropic_response(400),
                body={"error": {"type": "invalid_request_error", "code": "bad"}},
            ),
            "bad_request",
            False,
        ),
        (
            anthropic.InternalServerError(
                "server failed",
                response=_anthropic_response(500),
                body={"error": {"type": "api_error", "code": "server"}},
            ),
            "server",
            True,
        ),
    ],
)
def test_anthropic_adapter_maps_sdk_errors_to_runtime_error_info(
    exc: Exception,
    kind: str,
    retryable: bool,
):
    class FailingClaudeService(FakeClaudeService):
        def send_message(self, **kwargs):
            self.last_kwargs = kwargs
            raise exc

    adapter = AnthropicMessagesAdapter(service=FailingClaudeService({}))

    result = adapter.run_turn(
        RunRequest(provider="anthropic", model="claude-sonnet-4-6", purpose="chat")
    )

    assert result.status == "error"
    assert result.error_info is not None
    assert result.error_info.kind == kind
    assert result.error_info.retryable is retryable
    assert result.events[0].data["error_info"]["kind"] == kind


def test_anthropic_adapter_streams_sdk_exception_as_error_result():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    class FailingStreamClaudeService(FakeClaudeService):
        def stream_message(self, **kwargs):
            self.last_kwargs = kwargs
            on_text_delta = kwargs.get("on_text_delta")
            if on_text_delta:
                on_text_delta("partial")
            raise anthropic.APIConnectionError(
                message="connection failed",
                request=request,
            )

    adapter = AnthropicMessagesAdapter(service=FailingStreamClaudeService({}))

    events = list(
        adapter.stream_turn(
            RunRequest(provider="anthropic", model="claude-sonnet-4-6", purpose="chat")
        )
    )

    assert [event.type for event in events] == ["text_delta", "error", "final"]
    assert events[1].data["error_info"]["kind"] == "connection"
    assert events[-1].data["result"]["status"] == "error"
    assert events[-1].data["result"]["error_info"]["kind"] == "connection"


def test_anthropic_adapter_rejects_missing_named_tool_choice_before_sdk_call():
    service = FakeClaudeService({})
    adapter = AnthropicMessagesAdapter(service=service)
    tool = LocalToolSpec(
        name="search_sources",
        description="Search sources.",
        input_model=SearchInput,
    )

    with pytest.raises(ValueError, match="missing_tool"):
        adapter.run_turn(
            RunRequest(
                provider="anthropic",
                model="claude-sonnet-4-6",
                purpose="chat",
                tools=[tool],
                tool_choice=ToolChoice(type="tool", name="missing_tool"),
            )
        )

    assert service.last_kwargs is None


def test_anthropic_adapter_encodes_tool_results_with_claude_ordering():
    service = FakeClaudeService(
        {
            "content_blocks": [{"type": "text", "text": "Done."}],
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 12, "output_tokens": 2},
            "stop_reason": "end_turn",
        }
    )
    adapter = AnthropicMessagesAdapter(service=service)

    result = adapter.run_turn(
        RunRequest(
            provider="anthropic",
            model="claude-sonnet-4-6",
            purpose="chat",
            messages=[
                RunMessage(
                    role="assistant",
                    content=[
                        ToolCallPart(
                            call_id="toolu_1",
                            provider_call_id="toolu_1",
                            name="search_sources",
                            arguments={"query": "contracts"},
                        )
                    ],
                ),
                RunMessage(
                    role="tool",
                    content=[
                        ToolResultPart(
                            call_id="toolu_1",
                            name="search_sources",
                            content="result text",
                        )
                    ],
                ),
            ],
        )
    )

    assert service.last_kwargs["messages"] == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "search_sources",
                    "input": {"query": "contracts"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "result text",
                }
            ],
        },
    ]
    assert result.status == "complete"


def test_anthropic_adapter_streams_normalized_events():
    adapter = AnthropicMessagesAdapter(
        service=FakeClaudeService(
            {
                "content_blocks": [{"type": "text", "text": "hello"}],
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "stop_reason": "end_turn",
            }
        )
    )

    events = list(
        adapter.stream_turn(
            RunRequest(provider="anthropic", model="claude-sonnet-4-6", purpose="chat")
        )
    )

    assert [event.type for event in events[:2]] == ["text_delta", "text_delta"]
    assert events[-1].type == "final"


def test_anthropic_adapter_yields_deltas_before_stream_completes():
    service = BlockingStreamClaudeService(
        {
            "content_blocks": [{"type": "text", "text": "hello"}],
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }
    )
    adapter = AnthropicMessagesAdapter(service=service)

    events = adapter.stream_turn(
        RunRequest(provider="anthropic", model="claude-sonnet-4-6", purpose="chat")
    )
    first = next(events)

    assert first.type == "text_delta"
    assert first.data["delta"] == "hel"
    assert not service.returned.is_set()

    service.release.set()
    remaining = list(events)

    assert [event.type for event in remaining] == ["text_delta", "usage", "final"]
    assert remaining[0].data["delta"] == "lo"


def test_anthropic_adapter_replays_provider_document_title():
    service = FakeClaudeService(
        {
            "content_blocks": [{"type": "text", "text": "done"}],
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }
    )
    adapter = AnthropicMessagesAdapter(service=service)

    adapter.run_turn(
        RunRequest(
            provider="anthropic",
            model="claude-sonnet-4-6",
            purpose="pdf-extraction",
            messages=[
                RunMessage(
                    role="user",
                    content=[
                        MediaPart(
                            kind="document",
                            media_type="application/pdf",
                            data="encoded-page",
                            provider_metadata={
                                "anthropic": {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": "encoded-page",
                                    },
                                    "title": "sample.pdf - Page 3",
                                }
                            },
                        )
                    ],
                )
            ],
        )
    )

    sent_block = service.last_kwargs["messages"][0]["content"][0]
    assert sent_block["type"] == "document"
    assert sent_block["title"] == "sample.pdf - Page 3"


def test_anthropic_adapter_prompts_for_pydantic_structured_output():
    service = FakeClaudeService(
        {
            "content_blocks": [{"type": "text", "text": '{"value": "done"}'}],
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }
    )
    adapter = AnthropicMessagesAdapter(service=service)

    result = adapter.run_turn(
        RunRequest(
            provider="anthropic",
            model="claude-sonnet-4-6",
            purpose="structured",
            output_model=StructuredOutput,
        )
    )

    assert "output_config" not in service.last_kwargs
    assert "Return only a JSON object" in service.last_kwargs["system_prompt"]
    assert "StructuredOutput" in service.last_kwargs["system_prompt"]
    assert result.structured is not None
    assert result.structured.status == "parsed"
    assert result.structured.parsed == {"value": "done"}
