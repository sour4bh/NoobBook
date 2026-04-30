"""Executable tool bindings for the link extraction agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolContext, ToolSpec
from app.sources.link.run import web_agent_executor


def bind_link_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str | None,
) -> list[ToolSpec]:
    """Attach per-run link extraction handlers to static tool specs."""

    return bind_local_tools(
        specs,
        {
            "tavily_search": _dispatch_tool("tavily_search", project_id=project_id),
            "return_search_result": _dispatch_tool(
                "return_search_result",
                project_id=project_id,
            ),
        },
    )


def _dispatch_tool(tool_name: str, *, project_id: str | None):
    def handler(value: BaseModel, context: ToolContext) -> Any:
        tool_input = value.model_dump(mode="json", exclude_none=True)
        result, _ = web_agent_executor.dispatch(
            tool_name,
            tool_input,
            project_id=project_id,
        )
        if isinstance(result, str):
            return result
        return result

    return handler
