"""Executable tool bindings for the component agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.design.component.tool import component_tool_executor


def bind_component_tools(
    specs: Iterable[ToolSpec],
    *,
    context: dict[str, Any],
) -> list[ToolSpec]:
    """Attach component executor handlers."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _runtime_context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = component_tool_executor.dispatch(
                tool_name,
                tool_input,
                context,
            )
            if is_termination:
                return result
            return ToolOutput(
                content=result.get("message", str(result)),
                is_error=isinstance(result, dict) and not result.get("success", True),
            )

        return handler

    return bind_local_tools(
        specs,
        {
            "plan_components": dispatch("plan_components"),
            "write_component_code": dispatch("write_component_code"),
        },
    )
