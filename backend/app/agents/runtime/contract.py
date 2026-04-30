"""Provider-neutral run, message, event, and adapter contracts."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal, Optional, Protocol, Type, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from app.base.contracts import ContractModel
from app.agents.runtime.tool import ToolSpec


ProviderName = Literal["anthropic", "openai", "fake"]
ProviderErrorKind = Literal[
    "connection",
    "timeout",
    "rate_limit",
    "authentication",
    "permission",
    "bad_request",
    "not_found",
    "conflict",
    "unprocessable",
    "server",
    "incomplete",
    "cancelled",
    "unknown",
]


class Usage(ContractModel):
    """Provider usage normalized enough for app-owned cost accounting."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    provider_units: dict[str, int | float] = Field(default_factory=dict)


class ProviderState(ContractModel):
    """Opaque continuation state owned by a provider adapter."""

    provider: str
    values: dict[str, Any] = Field(default_factory=dict)


class ProviderErrorInfo(ContractModel):
    """Provider failure metadata normalized at the adapter boundary."""

    provider: str
    model: str
    kind: ProviderErrorKind
    message: str
    status_code: Optional[int] = None
    provider_error_type: Optional[str] = None
    provider_error_code: Optional[str] = None
    request_id: Optional[str] = None
    retryable: bool = False
    raw: Any = None


class TextPart(ContractModel):
    type: Literal["text"] = "text"
    text: str


class ToolCallPart(ContractModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    provider_call_id: Optional[str] = None


class ToolResultPart(ContractModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    name: str
    content: Any
    is_error: bool = False


class MediaPart(ContractModel):
    type: Literal["media"] = "media"
    kind: Literal["image", "document"]
    media_type: str
    data: Optional[str] = None
    url: Optional[str] = None
    file_id: Optional[str] = None
    filename: Optional[str] = None
    title: Optional[str] = None
    detail: Literal["auto", "low", "high"] = "auto"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderMetadataPart(ContractModel):
    type: Literal["provider_metadata"] = "provider_metadata"
    provider: str
    values: dict[str, Any] = Field(default_factory=dict)


ContentPart = TextPart | ToolCallPart | ToolResultPart | MediaPart | ProviderMetadataPart


class RunMessage(ContractModel):
    """Provider-neutral persisted/run-history message."""

    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentPart]


class ToolCall(ContractModel):
    """A model-requested tool invocation in runtime form."""

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    provider_call_id: Optional[str] = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(ContractModel):
    """A local or hosted tool result in runtime form."""

    call_id: str
    name: str
    content: Any
    is_error: bool = False


class StructuredResult(ContractModel):
    """Typed structured-output result with refusal and invalid states."""

    status: Literal["parsed", "refusal", "invalid"]
    parsed: Any = None
    refusal: Optional[str] = None
    error: Optional[str] = None
    raw: Any = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "StructuredResult":
        if self.status == "parsed" and self.parsed is None:
            raise ValueError("parsed structured result requires parsed payload")
        if self.status == "refusal" and not self.refusal:
            raise ValueError("refusal structured result requires refusal text")
        if self.status == "invalid" and not self.error:
            raise ValueError("invalid structured result requires error text")
        return self


class RunEvent(ContractModel):
    """Normalized event emitted by streaming and non-streaming runs."""

    type: Literal[
        "text_delta",
        "tool_call",
        "tool_result",
        "final",
        "usage",
        "provider_warning",
        "error",
    ]
    data: dict[str, Any] = Field(default_factory=dict)


class RunLimits(ContractModel):
    """Runtime loop and provider output limits."""

    max_tool_turns: int = 10
    max_output_tokens: int = 4096
    temperature: float = 0.0


class ToolChoice(ContractModel):
    """Provider-neutral tool-selection policy for one run."""

    type: Literal["auto", "any", "none", "tool"] = "auto"
    name: Optional[str] = None

    @model_validator(mode="after")
    def validate_named_tool(self) -> "ToolChoice":
        if self.type == "tool" and not self.name:
            raise ValueError("tool choice requires a tool name")
        if self.type != "tool" and self.name:
            raise ValueError("tool choice name is only valid for type='tool'")
        return self


class RunRequest(ContractModel):
    """Provider-neutral model run request."""

    provider: ProviderName | str
    model: str
    purpose: str
    system_prompt: Optional[str] = None
    messages: list[RunMessage] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    tool_choice: Optional[ToolChoice] = None
    output_model: Optional[Type[BaseModel]] = Field(default=None, exclude=True)
    limits: RunLimits = Field(default_factory=RunLimits)
    provider_state: Optional[ProviderState] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None
    chat_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunResult(ContractModel):
    """Provider-neutral result for one model turn or a completed run."""

    provider: ProviderName | str
    model: str
    status: Literal["complete", "requires_tools", "error"] = "complete"
    text: str = ""
    content: list[ContentPart] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    structured: Optional[StructuredResult] = None
    usage: Usage = Field(default_factory=Usage)
    provider_state: Optional[ProviderState] = None
    provider_request_ids: list[str] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
    generated_messages: list[RunMessage] = Field(default_factory=list)
    terminated_by_tools: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    error_info: Optional[ProviderErrorInfo] = None


STREAM_RESULT_FIELD = "result"


def final_event_data(
    result: RunResult,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Embed a complete turn result into the terminal stream event.

    Streaming progress events are intentionally lossy: they are suitable for UI
    progress, but not for reconstructing provider continuation state. The final
    provider response is the authoritative runtime result, so adapters attach it
    to their final event without recursively embedding the event list.
    """
    event_data = dict(data or {})
    event_data.setdefault("text", result.text)
    event_data.setdefault("status", result.status)
    event_data[STREAM_RESULT_FIELD] = result.model_dump(
        mode="json",
        exclude={"events"},
    )
    return event_data


def result_from_final_event(
    *,
    provider: str,
    model: str,
    data: dict[str, Any],
    events: list[RunEvent],
    error: Optional[str] = None,
    streamed_text: str = "",
) -> Optional[RunResult]:
    """Return the authoritative result carried by a final stream event."""
    raw_result = data.get(STREAM_RESULT_FIELD)
    if not isinstance(raw_result, dict):
        return None

    payload: dict[str, Any] = {
        str(key): value for key, value in raw_result.items()
    }
    payload.setdefault("provider", provider)
    payload.setdefault("model", model)
    result = RunResult.model_validate(payload)
    updates: dict[str, Any] = {"events": events}
    if streamed_text and not result.text:
        updates["text"] = streamed_text
    if error:
        updates["status"] = "error"
        updates["error"] = error
    return result.model_copy(update=updates)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol implemented by Anthropic, OpenAI, and test adapters."""

    name: str

    def compile_tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        """Compile runtime tools to the provider's request schema."""
        ...

    def run_turn(self, request: RunRequest) -> RunResult:
        """Run one provider turn and return normalized output."""
        ...

    def stream_turn(self, request: RunRequest) -> Iterator[RunEvent]:
        """Stream one provider turn as normalized runtime events."""
        ...

    def count_tokens(self, text: str, *, model: Optional[str] = None) -> int:
        """Return the provider's token count for text."""
        ...
