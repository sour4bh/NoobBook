"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class AnalyzeCsvDataInput(ContractModel):
    analysis_query: str = Field(description="Detailed description of what analysis to perform and what chart to generate. Be specific about:\n- What data to analyze (columns, filters, groupings)\n- What calculations to perform (sums, averages, percentages, trends)\n- What type of chart to create (bar, line, pie, scatter, heatmap)\n- Chart styling preferences (title, labels, colors)\n\nExamples:\n- 'Calculate total revenue by month and create a bar chart with blue bars, titled Monthly Revenue 2024'\n- 'Show the percentage distribution of sales by region as a pie chart'\n- 'Plot daily active users over time as a line chart with trend line'")
    csv_source_id: str = Field(description="The exact UUID of the CSV source to analyze. Copy the source_id UUID from the 'CSV DATA SOURCES' list in the user message (e.g., 'a1b2c3d4-e5f6-...'). Do NOT invent identifiers.")
    section_context: Optional[str] = Field(default=None, description='Which section of the report this analysis is for (helps with chart naming and context)')
class PlanBusinessReportInputSectionsItemModel(ContractModel):
    data_analysis: Optional[str] = Field(default=None, description='What data/chart is needed (optional)')
    title: str = Field(description='Section heading')
class PlanBusinessReportInput(ContractModel):
    key_question: Optional[str] = Field(default=None, description='The main question this report should answer')
    report_type: Literal['executive_summary', 'financial_report', 'performance_analysis', 'market_research', 'operations_report', 'sales_report', 'quarterly_review', 'annual_report'] = Field(description='Type of business report')
    sections: list[PlanBusinessReportInputSectionsItemModel] = Field(description='2-3 main sections for the report')
    title: str = Field(description="Report title (e.g., 'Q3 Sales Analysis')")
class SearchSourceContentInput(ContractModel):
    search_query: str = Field(description='What information to search for in this source. Be specific about the type of context needed.')
    section_context: Optional[str] = Field(default=None, description='Which section of the report this context is for')
    source_id: str = Field(description="The exact UUID of the source to search. Copy the source_id UUID from the 'CONTEXT SOURCES' list in the user message (e.g., 'a1b2c3d4-e5f6-...'). Do NOT invent identifiers.")
class WriteBusinessReportInput(ContractModel):
    charts_included: Optional[list[str]] = Field(default=None, description='Chart filenames referenced in the report')
    markdown_content: str = Field(description='REQUIRED: The complete business report in Markdown format (500-1000 words). Include:\n- Title and key findings\n- Chart references: ![Description](chart_filename.png)\n- Data tables if relevant\n- Recommendations')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='analyze_csv_data',
        description='Analyze CSV data and optionally generate charts. This tool internally uses the CSV analyzer agent which can run pandas code and generate matplotlib/seaborn visualizations. Call this tool for EACH separate analysis or chart you need. The tool returns analysis results and any generated chart filenames.',
        input_model=AnalyzeCsvDataInput,
        terminates_run=False,
        metadata={'registry_name': 'analyze_csv_data'},
    ),
    LocalToolSpec(
        name='plan_business_report',
        description='Plan a brief outline for the business report. Call this first to organize your approach.',
        input_model=PlanBusinessReportInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_business_report'},
    ),
    LocalToolSpec(
        name='search_source_content',
        description='Search for relevant content from non-CSV sources to add context to the report. Use this to find supporting information from documents, notes, or other text sources that can enrich the report with qualitative insights.',
        input_model=SearchSourceContentInput,
        terminates_run=False,
        metadata={'registry_name': 'search_source_content'},
    ),
    LocalToolSpec(
        name='write_business_report',
        description='Write the final business report in Markdown format. This is the TERMINATION tool - call it when ready to produce the final report.',
        input_model=WriteBusinessReportInput,
        terminates_run=True,
        metadata={'registry_name': 'write_business_report'},
    ),
)
