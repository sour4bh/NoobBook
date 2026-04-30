"""Typed tool specs for this domain-owned tool family."""

from typing import Any, Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class ReturnAnalysisInput(ContractModel):
    data_json: Optional[str] = Field(default=None, description='Optional JSON object string containing structured data from the analysis (key metrics, tables, etc.)')
    image_paths: Optional[list[str]] = Field(default=None, description='Paths to any generated plots/charts from the analysis')
    summary: str = Field(description='Summary of the analysis findings that answers the user question')
class RunAnalysisInputOperationModelFiltersItemModel(ContractModel):
    column: str
    operator: Literal['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'in']
    value: Any
class RunAnalysisInputOperationModelMetricsItemModel(ContractModel):
    column: Optional[str] = None
    function: Literal['count', 'sum', 'mean', 'median', 'min', 'max', 'nunique']
    name: Optional[str] = None
class RunAnalysisInputOperationModelSortItemModel(ContractModel):
    column: str
    direction: Optional[Literal['asc', 'desc']] = None
class RunAnalysisInputOperationModel(ContractModel):
    chart_type: Optional[Literal['bar', 'line', 'histogram']] = None
    columns: Optional[list[str]] = None
    filters: Optional[list[RunAnalysisInputOperationModelFiltersItemModel]] = None
    group_by: Optional[list[str]] = None
    kind: Literal['inspect', 'filter', 'aggregate', 'sort', 'chart']
    limit: Optional[int] = Field(default=None, ge=1, le=200)
    metrics: Optional[list[RunAnalysisInputOperationModelMetricsItemModel]] = None
    sort: Optional[list[RunAnalysisInputOperationModelSortItemModel]] = None
    title: Optional[str] = None
    x: Optional[str] = None
    y: Optional[str] = None
class RunAnalysisInput(ContractModel):
    operation: Optional[RunAnalysisInputOperationModel] = Field(default=None, description='One analysis operation. Use either operation or operations.')
    operations: Optional[list[RunAnalysisInputOperationModel]] = Field(default=None, description='Sequential operations. Use this instead of operation when more than one step is needed.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='return_analysis',
        description='Return the final analysis result. Call this when you have completed the analysis and are ready to provide the answer to the user.',
        input_model=ReturnAnalysisInput,
        terminates_run=True,
        metadata={'registry_name': 'return_analysis'},
    ),
    LocalToolSpec(
        name='run_analysis',
        description='Run a validated declarative table-analysis operation on the CSV data. Use inspect to understand columns, filter/sort to retrieve rows, aggregate for grouped metrics, and chart for simple bar/line/histogram plots. Do not provide Python code.',
        input_model=RunAnalysisInput,
        terminates_run=False,
        metadata={'registry_name': 'run_analysis'},
    ),
)
