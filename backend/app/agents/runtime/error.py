"""Runtime exception types."""

from __future__ import annotations

from typing import Optional

from app.agents.runtime.contract import ProviderErrorInfo, RunResult


class AgentRuntimeError(Exception):
    """Base class for provider-neutral runtime failures."""


class UnknownToolError(AgentRuntimeError):
    """Raised when a provider requests a tool not present in the run request."""


class ToolExecutionError(AgentRuntimeError):
    """Raised when local tool execution fails outside model-recoverable flow."""


class ToolResultError(AgentRuntimeError):
    """Raised when app code cannot consume a completed tool result."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        call_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.call_id = call_id


class ToolIterationLimitError(AgentRuntimeError):
    """Raised when a model exceeds the configured tool-turn limit."""


class ProviderRunError(AgentRuntimeError):
    """Raised when a provider returns a terminal failed run result."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        status: str = "error",
        provider_request_ids: Optional[list[str]] = None,
        partial_text: str = "",
        error_info: ProviderErrorInfo | None = None,
        result: RunResult | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status = status
        self.provider_request_ids = list(provider_request_ids or [])
        self.partial_text = partial_text
        self.error_info = error_info
        self.result = result

    @classmethod
    def from_result(cls, result: RunResult) -> "ProviderRunError":
        message = result.error or result.text or "Provider run failed"
        return cls(
            message,
            provider=str(result.provider),
            model=result.model,
            status=result.status,
            provider_request_ids=result.provider_request_ids,
            partial_text=result.text,
            error_info=result.error_info,
            result=result,
        )
