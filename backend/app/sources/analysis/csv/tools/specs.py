"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class AnalyzeCsvAgentInput(ContractModel):
    query: str = Field(description='The users question or analysis request. Can include requests for statistics, aggregations, filtering, grouping, comparisons, trends, or visualizations like bar charts, line graphs, pie charts etc.')
    source_id: str = Field(description='The ID of the CSV source to analyze (from available sources in your context)')
class CsvAnalyzerInput(ContractModel):
    aggregation: Optional[Literal['count', 'sum', 'mean', 'median', 'min', 'max']] = Field(default=None, description='Aggregation method for group_by operation. Count: frequency, Sum/Mean/Median: numeric aggregation, Min/Max: extreme values')
    column: Optional[str] = Field(default=None, description='Column name for single-column operations. Required for: statistics (numeric column), count_by_column, filter, group_by, top_bottom, unique_values (if columns not specified)')
    columns: Optional[list[str]] = Field(default=None, description='List of column names for multi-column operations. Optional for: profile (specific columns to profile), data_quality (specific columns to check), unique_values (multiple columns)')
    filename: str = Field(description='Name of the CSV file to analyze.')
    n: Optional[int] = Field(default=None, description='Number of items to return. Used in: top_bottom (top/bottom N values), unique_values (limit unique values shown)', ge=1, le=100)
    operation: Literal['summary', 'profile', 'statistics', 'count_by_column', 'filter', 'search', 'group_by', 'unique_values', 'data_quality', 'top_bottom'] = Field(description='Type of analysis to perform. Each operation provides different insights into your data.')
    operator: Optional[Literal['equals', 'not_equals', 'contains', 'not_contains', 'greater_than', 'less_than', 'greater_equal', 'less_equal']] = Field(default=None, description='Comparison operator for filter operation. Numeric operators: greater_than, less_than, greater_equal, less_equal. Text operators: contains, not_contains. Universal: equals, not_equals')
    search_term: Optional[str] = Field(default=None, description='Search term for finding text across all columns. Case-insensitive partial matching.')
    value: Optional[str] = Field(default=None, description="Value for filter operation. Can be numeric ('100', '50.5') or text ('active', 'pending'). Used with operator parameter.")
class ReturnCsvSummaryInput(ContractModel):
    column_count: Optional[int] = Field(default=None, description='Total number of columns in the CSV')
    row_count: Optional[int] = Field(default=None, description='Total number of rows in the CSV')
    summary: str = Field(description='Concise summary of the CSV dataset (300-400 tokens).')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='analyze_csv_agent',
        description='Trigger a data analysis agent for CSV files. Use this for any questions about CSV/spreadsheet data. The agent can perform in-depth analysis using pandas, calculate complex aggregations, filter and transform data, and generate visualizations (charts, graphs, plots) using matplotlib and seaborn. Do NOT use search_sources for CSV files - use this tool instead.',
        input_model=AnalyzeCsvAgentInput,
        terminates_run=False,
        metadata={'registry_name': 'analyze_csv_agent_tool'},
    ),
    LocalToolSpec(
        name='csv_analyzer',
        description='Advanced CSV analyzer for analytics. Handles large datasets with intelligent data type detection, statistical analysis, data profiling, quality assessment, and business insights. Perfect for analyzing any structured CSV data. Also if you require only summary call the sumamry operation and pass the file name just to get the sumamry',
        input_model=CsvAnalyzerInput,
        terminates_run=False,
        metadata={'registry_name': 'csv_analyser'},
    ),
    LocalToolSpec(
        name='return_csv_summary',
        description='Return the final CSV analysis summary. Call this when you have analyzed the CSV and are ready to provide the summary.',
        input_model=ReturnCsvSummaryInput,
        terminates_run=True,
        metadata={'registry_name': 'return_csv_summary'},
    ),
)
