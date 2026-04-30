"""Typed tool specs for this domain-owned tool family."""

from typing import Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class AnalyzeDatabaseAgentInput(ContractModel):
    query: str = Field(description="The user's question or analysis request. Examples: 'Top 10 customers by revenue last month', 'Daily active users for the last 30 days', 'How many orders were refunded by reason?'")
    source_id: str = Field(description='The ID of the DATABASE source to analyze (from available sources in your context)')
class QueryRunnerInput(ContractModel):
    query: str = Field(description='A SQL SELECT/WITH query to execute. Only read-only queries are allowed.')
class ReturnDatabaseResultInput(ContractModel):
    findings: Optional[list[str]] = Field(default=None, description='Key findings or takeaways (bulleted).')
    sql_queries: Optional[list[str]] = Field(default=None, description='SQL queries executed (for transparency / debugging).')
    summary: str = Field(description='Concise, user-facing answer with concrete numbers and explanations.')
class SchemaFetcherInput(ContractModel):
    table_names: Optional[list[str]] = Field(default=None, description='Optional list of table names to fetch detailed schema for. Only pass table names you discovered from a previous schema_fetcher call or that the user explicitly mentioned.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='analyze_database_agent',
        description='Trigger a database query agent for DATABASE sources (Postgres/MySQL). Use this when the user asks questions that require LIVE data from a connected database (counts, metrics, lists, trends). The agent will inspect schema, write safe read-only SQL (SELECT only), execute queries, and return a clear answer. Do NOT write to the database.',
        input_model=AnalyzeDatabaseAgentInput,
        terminates_run=False,
        metadata={'registry_name': 'analyze_database_agent_tool'},
    ),
    LocalToolSpec(
        name='query_runner',
        description='Execute a read-only SQL query (SELECT/WITH only) on the current DATABASE source. Never write/modify data. Prefer adding LIMIT 100 (or smaller) to keep results small.',
        input_model=QueryRunnerInput,
        terminates_run=False,
        metadata={'registry_name': 'query_runner'},
    ),
    LocalToolSpec(
        name='return_database_result',
        description='Return your final answer after you have gathered enough evidence from schema_fetcher/query_runner. Always call this tool to finish.',
        input_model=ReturnDatabaseResultInput,
        terminates_run=True,
        metadata={'registry_name': 'return_database_result'},
    ),
    LocalToolSpec(
        name='schema_fetcher',
        description='Fetch the schema for the current DATABASE source. If table_names is omitted/empty, returns an overview list of tables/views. If table_names is provided, returns detailed column/keys info for those tables. Do NOT guess table names—call without table_names first to discover them.',
        input_model=SchemaFetcherInput,
        terminates_run=False,
        metadata={'registry_name': 'schema_fetcher'},
    ),
)
