"""Executable tool bindings for the website agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.design.website.tool import website_tool_executor


def bind_website_tools(
    specs: Iterable[ToolSpec],
    *,
    context: dict[str, Any],
) -> list[ToolSpec]:
    """Attach website executor handlers with generated file/image state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _runtime_context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = website_tool_executor.dispatch(
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
            "plan_website": dispatch("plan_website"),
            "generate_website_image": dispatch("generate_website_image"),
            "read_file": dispatch("read_file"),
            "create_file": dispatch("create_file"),
            "update_file_lines": dispatch("update_file_lines"),
            "insert_code": dispatch("insert_code"),
            "finalize_website": dispatch("finalize_website"),
        },
    )
