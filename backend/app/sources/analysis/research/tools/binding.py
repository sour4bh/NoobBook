"""Executable tool bindings for the deep research agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolSpec
from app.sources.analysis.research.tool import deep_research_executor


def bind_research_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    output_path: str,
    segments_written: list[int],
) -> list[ToolSpec]:
    """Attach research handlers and segment-count state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _context: Any) -> str:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            if tool_name == "write_research_to_file":
                segments_written[0] += 1
            result, _ = deep_research_executor.research(
                tool_name=tool_name,
                tool_input=tool_input,
                output_path=output_path,
                project_id=project_id,
            )
            return result

        return handler

    return bind_local_tools(
        specs,
        {
            "tavily_search_advance": dispatch("tavily_search_advance"),
            "write_research_to_file": dispatch("write_research_to_file"),
        },
    )
