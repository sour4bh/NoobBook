"""Executable tool bindings for the wireframe agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.design.wireframe.tool import wireframe_tool_executor


def bind_wireframe_tools(
    specs: Iterable[ToolSpec],
    *,
    context: dict[str, Any],
) -> list[ToolSpec]:
    """Attach wireframe executor handlers with accumulated state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _runtime_context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = wireframe_tool_executor.dispatch(
                tool_name,
                tool_input,
                context,
            )
            if "accumulated_elements" in result:
                context["accumulated_elements"] = result["accumulated_elements"]
            if "wireframe_metadata" in result:
                context["wireframe_metadata"] = result["wireframe_metadata"]
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
            "plan_wireframe": dispatch("plan_wireframe"),
            "add_wireframe_section": dispatch("add_wireframe_section"),
            "finalize_wireframe": dispatch("finalize_wireframe"),
            "generate_wireframe": dispatch("generate_wireframe"),
        },
    )
