"""Executable tool bindings for the CSV analysis agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.sources.analysis.csv.run import analysis_executor


def bind_csv_analysis_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    source_id: str,
    generated_plots: list[str],
) -> list[ToolSpec]:
    """Attach CSV executor handlers and per-run plot state."""

    def run_analysis(value: BaseModel, _context: Any) -> str | ToolOutput:
        tool_input = value.model_dump(mode="json", exclude_none=True)
        result, _ = analysis_executor.dispatch(
            "run_analysis",
            tool_input,
            project_id,
            source_id,
        )
        if result.get("plot_filenames"):
            generated_plots.extend(result["plot_filenames"])
        if not result.get("success"):
            return ToolOutput(
                content=f"Error: {result.get('error', 'Unknown error')}",
                is_error=True,
            )
        return result.get("output", "Analysis completed")

    def return_analysis(value: BaseModel, _context: Any) -> dict[str, Any]:
        tool_input = value.model_dump(mode="json", exclude_none=True)
        result, _ = analysis_executor.dispatch(
            "return_analysis",
            tool_input,
            project_id,
            source_id,
        )
        if generated_plots:
            result["image_paths"] = generated_plots
        return result

    return bind_local_tools(
        specs,
        {
            "run_analysis": run_analysis,
            "return_analysis": return_analysis,
        },
    )
