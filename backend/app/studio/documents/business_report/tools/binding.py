"""Executable tool bindings for the business report agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.documents.business_report.tool import business_report_tool_executor


def bind_business_report_tools(
    specs: Iterable[ToolSpec],
    *,
    context: dict[str, Any],
) -> list[ToolSpec]:
    """Attach business report executor handlers with per-run context."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _runtime_context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = business_report_tool_executor.dispatch(
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
            "plan_business_report": dispatch("plan_business_report"),
            "analyze_csv_data": dispatch("analyze_csv_data"),
            "search_source_content": dispatch("search_source_content"),
            "write_business_report": dispatch("write_business_report"),
        },
    )
