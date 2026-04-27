"""Declarative CSV analysis executor."""

import io
import logging
import uuid
from typing import Any, Dict, Literal, Optional, Self, Tuple

import pandas as pd
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.providers.supabase import storage_service


logger = logging.getLogger(__name__)


class FilterSpec(BaseModel):
    column: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"]
    value: Any


class SortSpec(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class MetricSpec(BaseModel):
    column: Optional[str] = None
    function: Literal["count", "sum", "mean", "median", "min", "max", "nunique"]
    name: Optional[str] = None

    @model_validator(mode="after")
    def _require_column_for_non_count(self) -> Self:
        if self.function != "count" and not self.column:
            raise ValueError(f"{self.function} metric requires column")
        return self


class OperationSpec(BaseModel):
    kind: Literal["inspect", "filter", "aggregate", "sort", "chart"]
    columns: list[str] = Field(default_factory=list)
    filters: list[FilterSpec] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    metrics: list[MetricSpec] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=200)
    chart_type: Literal["bar", "line", "histogram"] = "bar"
    x: Optional[str] = None
    y: Optional[str] = None
    title: Optional[str] = None


class AnalysisRequest(BaseModel):
    operation: Optional[OperationSpec] = None
    operations: list[OperationSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_operation(self) -> Self:
        if self.operation and self.operations:
            raise ValueError("Provide either operation or operations, not both")
        if not self.operation and not self.operations:
            raise ValueError("Provide operation or operations")
        return self

    def ordered_operations(self) -> list[OperationSpec]:
        return [self.operation] if self.operation else self.operations


class AnalysisExecutor:
    """Executor for validated table-analysis operations on CSV data."""

    def __init__(self) -> None:
        self._df_cache: Dict[str, pd.DataFrame] = {}

    def dispatch(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        project_id: str,
        source_id: str
    ) -> Tuple[Dict[str, Any], bool]:
        if tool_name == "run_analysis":
            return self._run_analysis(tool_input, project_id, source_id), False
        if tool_name == "return_analysis":
            return tool_input, True
        return {"success": False, "error": f"Unknown tool: {tool_name}"}, False

    def _load_dataframe(self, project_id: str, source_id: str) -> pd.DataFrame:
        cache_key = f"{project_id}_{source_id}"

        if cache_key not in self._df_cache:
            csv_bytes = storage_service.download_raw_file(
                project_id, source_id, f"{source_id}.csv"
            )
            if csv_bytes is None:
                raise FileNotFoundError(
                    f"CSV file not found in storage: {source_id}.csv"
                )
            self._df_cache[cache_key] = pd.read_csv(io.BytesIO(csv_bytes))

        return self._df_cache[cache_key].copy()

    def _run_analysis(
        self,
        tool_input: Dict[str, Any],
        project_id: str,
        source_id: str
    ) -> Dict[str, Any]:
        try:
            request = AnalysisRequest.model_validate(tool_input)
        except ValidationError as error:
            return {"success": False, "error": f"Invalid analysis request: {error}"}

        try:
            current = self._load_dataframe(project_id, source_id)
            outputs: list[str] = []
            plot_filenames: list[str] = []
            data: Any = None

            for operation in request.ordered_operations():
                self._validate_columns(current, operation)
                current, output, data, plots = self._apply_operation(
                    current, operation, project_id, source_id
                )
                outputs.append(output)
                plot_filenames.extend(plots)

            result: Dict[str, Any] = {
                "success": True,
                "output": "\n\n".join(outputs) or "Analysis completed",
                "data": data,
            }
            if plot_filenames:
                result["plot_filenames"] = plot_filenames
            return result
        except Exception as error:
            logger.exception("Declarative CSV analysis failed")
            return {"success": False, "error": f"Analysis error: {error}"}

    def _validate_columns(self, df: pd.DataFrame, operation: OperationSpec) -> None:
        columns = set(df.columns)
        requested = set(operation.columns)
        requested.update(f.column for f in operation.filters)
        if operation.kind != "aggregate":
            requested.update(s.column for s in operation.sort)
        requested.update(operation.group_by)
        requested.update(metric.column for metric in operation.metrics if metric.column)
        requested.update(value for value in (operation.x, operation.y) if value)
        missing = sorted(column for column in requested if column not in columns)
        if missing:
            raise ValueError(f"Unknown column(s): {', '.join(missing)}")

    def _apply_operation(
        self,
        df: pd.DataFrame,
        operation: OperationSpec,
        project_id: str,
        source_id: str,
    ) -> Tuple[pd.DataFrame, str, Any, list[str]]:
        filtered = self._apply_filters(df, operation.filters)

        if operation.kind == "inspect":
            view = filtered[operation.columns] if operation.columns else filtered
            data = {
                "rows": int(len(view)),
                "columns": list(view.columns),
                "dtypes": {column: str(dtype) for column, dtype in view.dtypes.items()},
                "preview": view.head(operation.limit).to_dict(orient="records"),
            }
            return filtered, self._format_data(data), data, []

        if operation.kind == "filter":
            view = self._apply_sort(filtered, operation.sort).head(operation.limit)
            data = view.to_dict(orient="records")
            return view, self._format_dataframe(view), data, []

        if operation.kind == "sort":
            view = self._apply_sort(filtered, operation.sort).head(operation.limit)
            data = view.to_dict(orient="records")
            return view, self._format_dataframe(view), data, []

        if operation.kind == "aggregate":
            view = self._aggregate(filtered, operation)
            data = view.to_dict(orient="records")
            return view, self._format_dataframe(view), data, []

        filename = self._chart(filtered, operation, project_id, source_id)
        data = {"plot_filenames": [filename]}
        return filtered, f"Chart saved as: {filename}", data, [filename]

    def _apply_filters(self, df: pd.DataFrame, filters: list[FilterSpec]) -> pd.DataFrame:
        current = df
        for spec in filters:
            series = current[spec.column]
            if spec.operator == "eq":
                mask = series == spec.value
            elif spec.operator == "ne":
                mask = series != spec.value
            elif spec.operator == "gt":
                mask = series > spec.value
            elif spec.operator == "gte":
                mask = series >= spec.value
            elif spec.operator == "lt":
                mask = series < spec.value
            elif spec.operator == "lte":
                mask = series <= spec.value
            elif spec.operator == "contains":
                mask = series.astype(str).str.contains(str(spec.value), case=False, na=False)
            elif spec.operator == "in":
                if not isinstance(spec.value, list):
                    raise ValueError("operator 'in' requires a list value")
                mask = series.isin(spec.value)
            current = current[mask]
        return current

    def _apply_sort(self, df: pd.DataFrame, sort: list[SortSpec]) -> pd.DataFrame:
        if not sort:
            return df
        return df.sort_values(
            by=[spec.column for spec in sort],
            ascending=[spec.direction == "asc" for spec in sort],
        )

    def _aggregate(self, df: pd.DataFrame, operation: OperationSpec) -> pd.DataFrame:
        if not operation.metrics:
            raise ValueError("aggregate operation requires metrics")

        if operation.group_by:
            grouped = df.groupby(operation.group_by, dropna=False)
            frames = []
            for metric in operation.metrics:
                name = metric.name or (
                    f"{metric.function}_{metric.column}" if metric.column else "count"
                )
                if metric.function == "count":
                    series = grouped.size().rename(name)
                else:
                    series = getattr(grouped[metric.column], metric.function)().rename(name)
                frames.append(series)
            result = pd.concat(frames, axis=1).reset_index()
        else:
            row = {}
            for metric in operation.metrics:
                name = metric.name or (
                    f"{metric.function}_{metric.column}" if metric.column else "count"
                )
                row[name] = int(len(df)) if metric.function == "count" else getattr(df[metric.column], metric.function)()
            result = pd.DataFrame([row])

        missing_sort = sorted(spec.column for spec in operation.sort if spec.column not in result.columns)
        if missing_sort:
            raise ValueError(f"Unknown column(s): {', '.join(missing_sort)}")

        return self._apply_sort(result, operation.sort).head(operation.limit)

    def _chart(
        self,
        df: pd.DataFrame,
        operation: OperationSpec,
        project_id: str,
        source_id: str,
    ) -> str:
        if not operation.x:
            raise ValueError("chart operation requires x")
        if operation.chart_type in {"bar", "line"} and not operation.y:
            raise ValueError(f"{operation.chart_type} chart requires y")

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        view = self._apply_sort(df, operation.sort).head(operation.limit)

        if operation.chart_type == "histogram":
            view[operation.x].plot(kind="hist", ax=ax)
        elif operation.chart_type == "line":
            view.plot(kind="line", x=operation.x, y=operation.y, ax=ax)
        else:
            view.plot(kind="bar", x=operation.x, y=operation.y, ax=ax)

        ax.set_title(operation.title or f"{operation.chart_type.title()} chart")
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buffer.seek(0)

        filename = f"{source_id}_plot_{uuid.uuid4()}.png"
        uploaded = storage_service.upload_ai_image(project_id, filename, buffer.read())
        if not uploaded:
            raise RuntimeError(f"Plot upload failed: {filename}")
        return filename

    def _format_dataframe(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "No rows matched the requested operation."
        return df.to_string(index=False)

    def _format_data(self, data: Dict[str, Any]) -> str:
        lines = [
            f"Rows: {data['rows']}",
            f"Columns: {', '.join(data['columns'])}",
            "Dtypes:",
        ]
        lines.extend(f"- {column}: {dtype}" for column, dtype in data["dtypes"].items())
        if data["preview"]:
            lines.append("Preview:")
            lines.append(pd.DataFrame(data["preview"]).to_string(index=False))
        return "\n".join(lines)

    def clear_cache(
        self,
        project_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> None:
        if project_id and source_id:
            cache_key = f"{project_id}_{source_id}"
            self._df_cache.pop(cache_key, None)
        else:
            self._df_cache.clear()


analysis_executor = AnalysisExecutor()
