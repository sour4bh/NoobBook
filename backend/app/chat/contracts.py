from typing import Any, Literal, Optional

from pydantic import Field, RootModel, model_validator

from app.agents.runtime.contract import ContentPart
from app.base.contracts import ContractModel


class MessageContent(RootModel[list[ContentPart]]):
    """Current `messages.content` JSONB contract.

    NBB-1106 stores neutral runtime content parts. Legacy Anthropic block
    shapes are migration input only and are converted before validation.
    """

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
