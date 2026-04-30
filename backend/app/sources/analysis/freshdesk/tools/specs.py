"""Typed tool specs for this domain-owned tool family."""

from typing import Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class AnalyzeFreshdeskAgentInput(ContractModel):
    query: str = Field(description='Question about Freshdesk tickets')
    source_id: str = Field(description='The FRESHDESK source ID')
class QueryRunnerInput(ContractModel):
    explanation: str = Field(description='What this query analyzes')
    sql_query: str = Field(description='SELECT SQL query')
class ReturnTicketAnalysisInput(ContractModel):
    findings: list[str]
    recommendations: Optional[list[str]] = None
    summary: str
class SchemaInfoInput(ContractModel):
    pass


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='analyze_freshdesk_agent',
        description='Trigger a Freshdesk ticket analysis agent for support ticket analysis.',
        input_model=AnalyzeFreshdeskAgentInput,
        terminates_run=False,
        metadata={'registry_name': 'analyze_freshdesk_agent_tool'},
    ),
    LocalToolSpec(
        name='query_runner',
        description='Execute read-only SQL against freshdesk_tickets table.',
        input_model=QueryRunnerInput,
        terminates_run=False,
        metadata={'registry_name': 'query_runner'},
    ),
    LocalToolSpec(
        name='return_ticket_analysis',
        description='Return final analysis with structured insights.',
        input_model=ReturnTicketAnalysisInput,
        terminates_run=True,
        metadata={'registry_name': 'return_ticket_analysis'},
    ),
    LocalToolSpec(
        name='schema_info',
        description='Get freshdesk_tickets schema and ticket count.',
        input_model=SchemaInfoInput,
        terminates_run=False,
        metadata={'registry_name': 'schema_info'},
    ),
)
