"""Executable tool bindings for the database analysis agent."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.sources.analysis.database.tool import DatabaseExecutor


def bind_database_tools(
    specs: Iterable[ToolSpec],
    *,
    executor: DatabaseExecutor,
    project_id: str,
    source_id: str,
    executed_queries: list[str],
) -> list[ToolSpec]:
    """Attach database executor handlers and per-run query state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _context: Any) -> Any:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = executor.query(
                tool_name,
                tool_input,
                project_id,
                source_id,
            )
            if tool_name == "query_runner" and isinstance(tool_input.get("query"), str):
                executed_queries.append(tool_input["query"])
            if is_termination:
                if isinstance(result, dict) and not result.get("sql_queries"):
                    result["sql_queries"] = executed_queries
                return result
            return ToolOutput(
                content=_format_tool_result(result),
                is_error=isinstance(result, dict) and not result.get("success", True),
            )

        return handler

    return bind_local_tools(
        specs,
        {
            "schema_fetcher": dispatch("schema_fetcher"),
            "query_runner": dispatch("query_runner"),
            "return_database_result": dispatch("return_database_result"),
        },
    )


def _format_tool_result(result: dict[str, Any]) -> str:
    if not result.get("success"):
        return f"Error: {result.get('error', 'Unknown error')}"
    try:
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception:
        return str(result)
