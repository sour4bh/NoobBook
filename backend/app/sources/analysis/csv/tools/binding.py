"""Executable tool bindings for CSV source summarization."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.sources.analysis.csv.tool import csv_tool_executor


def bind_csv_summary_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    source_id: str,
    csv_file_path: str | None,
) -> list[ToolSpec]:
    """Attach CSV summary handlers to static specs."""

    def csv_analyzer(value: BaseModel, _context: Any) -> ToolOutput:
        tool_input = value.model_dump(mode="json", exclude_none=True)
        result, _ = csv_tool_executor.analyze(
            tool_input,
            project_id,
            source_id,
            csv_file_path=csv_file_path,
        )
        return ToolOutput(
            content=_format_tool_result(result),
            is_error=not result.get("success", False),
        )

    def return_csv_summary(value: BaseModel, _context: Any) -> dict[str, Any]:
        return value.model_dump(mode="json", exclude_none=True)

    return bind_local_tools(
        specs,
        {
            "csv_analyzer": csv_analyzer,
            "return_csv_summary": return_csv_summary,
        },
    )


def _format_tool_result(result: dict[str, Any]) -> str:
    if not result.get("success"):
        return f"Error: {result.get('error', 'Unknown error')}"

    operation = result.get("operation", "unknown")
    output_parts = [f"## CSV Analysis Result ({operation})"]

    if operation == "summary":
        output_parts.append(f"\nRows: {result.get('total_rows', 0)}")
        output_parts.append(f"Columns: {result.get('total_columns', 0)}")

        output_parts.append("\n### Column Information")
        column_info = result.get("column_info", {})
        for col, info in column_info.items():
            col_type = info.get("type", "unknown")
            non_empty = info.get("non_empty", 0)
            unique = info.get("unique", 0)
            output_parts.append(
                f"- {col} ({col_type}): {non_empty} values, {unique} unique"
            )

        sample_data = result.get("sample_data", [])
        if sample_data:
            output_parts.append("\n### Sample Data (First 3 Rows)")
            for index, row in enumerate(sample_data[:3], 1):
                row_str = ", ".join(
                    f"{key}: {value}" for key, value in list(row.items())[:5]
                )
                output_parts.append(f"{index}. {row_str}")

        recommendations = result.get("recommendations", [])
        if recommendations:
            output_parts.append("\n### Recommendations")
            for recommendation in recommendations:
                output_parts.append(f"- {recommendation}")

    elif operation == "profile":
        output_parts.append(f"\nRows: {result.get('row_count', 0)}")
        output_parts.append(f"Columns: {result.get('column_count', 0)}")
        output_parts.append(f"Quality Score: {result.get('data_quality_score', 0)}%")

        output_parts.append("\n### Column Profiles")
        profiles = result.get("column_profiles", {})
        for col, profile in profiles.items():
            output_parts.append(f"\n**{col}** ({profile.get('type', 'unknown')})")
            output_parts.append(
                f"  Completeness: {profile.get('completeness', 'N/A')}"
            )
            output_parts.append(f"  Unique: {profile.get('unique_values', 0)}")
            if "mean" in profile:
                output_parts.append(
                    f"  Mean: {profile.get('mean')}, Median: {profile.get('median')}"
                )
    else:
        output_parts.append(f"\n{json.dumps(result, indent=2, default=str)}")

    return "\n".join(output_parts)
