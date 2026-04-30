"""Fake provider adapters for runtime contract tests."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Optional

from app.agents.runtime.contract import RunEvent, RunRequest, RunResult, Usage
from app.agents.runtime.tool import LocalToolSpec, McpProxyToolSpec, ToolSpec
from app.providers.anthropic.schema import tool_schema as anthropic_tool_schema


class ScriptedProviderAdapter:
    """Deterministic provider adapter that returns scripted turn results."""

    name = "fake"

    def __init__(
        self,
        results: Sequence[RunResult],
        stream_events: Sequence[RunEvent] | None = None,
    ) -> None:
        self._results = list(results)
        self._stream_events = list(stream_events or [])
        self.requests: list[RunRequest] = []

    def compile_tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [
            anthropic_tool_schema(tool)
            for tool in tools
            if isinstance(tool, (LocalToolSpec, McpProxyToolSpec))
        ]

    def run_turn(self, request: RunRequest) -> RunResult:
        self.requests.append(request)
        if not self._results:
            return RunResult(
                provider="fake",
                model=request.model,
                status="complete",
                usage=Usage(),
            )
        return self._results.pop(0)

    def stream_turn(self, request: RunRequest) -> Iterator[RunEvent]:
        self.requests.append(request)
        yield from self._stream_events

    def count_tokens(self, text: str, *, model: Optional[str] = None) -> int:
        return len(text.split())
