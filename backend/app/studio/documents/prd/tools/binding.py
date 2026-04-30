"""Executable tool bindings for the PRD agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.documents.prd.tool import prd_tool_executor


def bind_prd_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    job_id: str,
    source_id: str | None,
    sections_written: list[int],
) -> list[ToolSpec]:
    """Attach PRD executor handlers and section-count state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = prd_tool_executor.dispatch(
                tool_name,
                tool_input,
                {
                    "project_id": project_id,
                    "job_id": job_id,
                    "source_id": source_id,
                    "sections_written": sections_written[0],
                    "iterations": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            )
            if tool_name == "write_prd_section":
                sections_written[0] += 1
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
            "plan_prd": dispatch("plan_prd"),
            "write_prd_section": dispatch("write_prd_section"),
        },
    )
