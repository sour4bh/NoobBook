"""Executable tool bindings for the presentation agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.documents.presentation.tool import presentation_tool_executor


def bind_presentation_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    job_id: str,
    source_id: str,
    created_files: list[str],
    slides_info: list[dict[str, Any]],
) -> list[ToolSpec]:
    """Attach presentation executor handlers and mutable run state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = presentation_tool_executor.dispatch(
                tool_name,
                tool_input,
                {
                    "project_id": project_id,
                    "job_id": job_id,
                    "source_id": source_id,
                    "created_files": created_files,
                    "slides_info": slides_info,
                    "iterations": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            )
            if result.get("created_files"):
                created_files[:] = result["created_files"]
            if result.get("slides_info"):
                slides_info[:] = result["slides_info"]
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
            "plan_presentation": dispatch("plan_presentation"),
            "create_base_styles": dispatch("create_base_styles"),
            "create_slide": dispatch("create_slide"),
            "finalize_presentation": dispatch("finalize_presentation"),
        },
    )
