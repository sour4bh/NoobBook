"""Executable tool bindings for the Freshdesk analysis agent."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.sources.analysis.freshdesk.tool import freshdesk_executor


def bind_freshdesk_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    source_id: str,
    executed_queries: list[str],
) -> list[ToolSpec]:
    """Attach Freshdesk executor handlers and query tracking."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _context: Any) -> Any:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = freshdesk_executor.fetch(
                tool_name,
                tool_input,
                project_id,
                source_id,
            )
            if tool_name == "query_runner" and tool_input.get("sql_query"):
                executed_queries.append(str(tool_input["sql_query"]))
            if is_termination:
                return result
            return ToolOutput(
                content=json.dumps(result) if isinstance(result, dict) else str(result),
                is_error=isinstance(result, dict) and not result.get("success", True),
            )

        return handler

    return bind_local_tools(
        specs,
        {
            "schema_info": dispatch("schema_info"),
            "query_runner": dispatch("query_runner"),
            "return_ticket_analysis": dispatch("return_ticket_analysis"),
        },
    )
