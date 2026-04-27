from typing import Any, Literal, Optional, Union

from pydantic import Field, RootModel, model_validator

from app.base.contracts import ContractModel


class TextBlock(ContractModel):
    type: Literal["text"] = "text"
    text: str
    citations: Optional[list[dict[str, Any]]] = None


class ToolUseBlock(ContractModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(ContractModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: Optional[bool] = None


class ServerToolUseBlock(ContractModel):
    type: Literal["server_tool_use"] = "server_tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class WebSearchToolResultBlock(ContractModel):
    type: Literal["web_search_tool_result"] = "web_search_tool_result"
    tool_use_id: str
    content: Any


class WebFetchToolResultBlock(ContractModel):
    type: Literal["web_fetch_tool_result"] = "web_fetch_tool_result"
    tool_use_id: str
    content: Any


ContentBlock = Union[
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ServerToolUseBlock,
    WebSearchToolResultBlock,
    WebFetchToolResultBlock,
]


class StoredTextContent(ContractModel):
    text: str
    error: Optional[bool] = None


class MessageContent(RootModel[Union[StoredTextContent, list[ContentBlock]]]):
    pass


class StoredMessage(ContractModel):
    id: str
    role: Literal["user", "assistant"]
    content: Any
    created_at: Optional[str] = None
    model: Optional[str] = None
    tokens: Optional[dict[str, Any]] = None
    error: Optional[bool] = None


class ChatMessageResponse(ContractModel):
    success: Literal[True] = True
    user_message: dict[str, Any]
    assistant_message: dict[str, Any]


class ChatStreamEvent(ContractModel):
    event: Literal[
        "user_message",
        "ping",
        "assistant_delta",
        "assistant_done",
        "error",
    ]
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self) -> "ChatStreamEvent":
        if self.event == "assistant_delta" and not isinstance(self.data.get("delta"), str):
            raise ValueError("assistant_delta requires data.delta")
        if self.event == "error" and not isinstance(self.data.get("message"), str):
            raise ValueError("error requires data.message")
        if self.event == "ping" and self.data:
            raise ValueError("ping payload must be empty")
        return self
