"""Helpers for consuming completed runtime tool results."""

from __future__ import annotations

from typing import TypeVar, cast

from app.agents.runtime.contract import RunResult, ToolResult
from app.agents.runtime.error import ToolResultError


T = TypeVar("T")


def successful_tool_results(result: RunResult, name: str) -> list[ToolResult]:
    """Return successful tool results for a runtime tool name."""
    matches = [item for item in result.tool_results if item.name == name]
    if not matches:
        raise ToolResultError(f"Tool {name!r} did not return a result")

    for item in matches:
        if item.is_error:
            raise ToolResultError(
                f"Tool {name!r} returned an error: {item.content}",
                tool_name=name,
                call_id=item.call_id,
            )
    return matches


def tool_result_payloads(
    result: RunResult,
    name: str,
    expected_type: type[T],
) -> list[T]:
    """Return successful tool result payloads with a concrete runtime type."""
    payloads: list[T] = []
    for item in successful_tool_results(result, name):
        if not isinstance(item.content, expected_type):
            raise ToolResultError(
                f"Tool {name!r} returned {type(item.content).__name__}, "
                f"expected {expected_type.__name__}",
                tool_name=name,
                call_id=item.call_id,
            )
        payloads.append(cast(T, item.content))
    return payloads


def require_tool_result_payload(
    result: RunResult,
    name: str,
    expected_type: type[T],
) -> T:
    """Return the first successful tool result payload for a runtime tool name."""
    return tool_result_payloads(result, name, expected_type)[0]
