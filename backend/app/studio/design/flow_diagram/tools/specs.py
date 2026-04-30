"""Typed tool specs for this domain-owned tool family."""

from typing import Literal

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class GenerateFlowDiagramInput(ContractModel):
    description: str = Field(description='A brief explanation of what the diagram represents (1-2 sentences)')
    diagram_type: Literal['flowchart', 'sequence', 'state', 'er', 'class', 'pie', 'gantt', 'journey', 'mindmap'] = Field(description='The type of Mermaid diagram being generated')
    mermaid_syntax: str = Field(description='Valid Mermaid diagram syntax. Must start with diagram type declaration (graph, flowchart, sequenceDiagram, stateDiagram-v2, erDiagram, pie, gantt, classDiagram, etc.)')
    title: str = Field(description='A short descriptive title for the diagram (max 10 words)')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='generate_flow_diagram',
        description='Generate a Mermaid diagram representing processes, workflows, sequences, or relationships from the content. Supports flowcharts, sequence diagrams, state diagrams, ER diagrams, and more.',
        input_model=GenerateFlowDiagramInput,
        terminates_run=True,
        metadata={'registry_name': 'flow_diagram_tool'},
    ),
)
