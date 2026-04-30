"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class PlanPrdInputSectionsItemModel(ContractModel):
    description: str = Field(description='Brief description of what this section will cover')
    priority: Optional[Literal['essential', 'important', 'optional']] = Field(default=None, description='How critical this section is for the PRD')
    section_id: str = Field(description="Unique identifier for the section (e.g., '1', '2', '2.1')")
    title: str = Field(description="Section title (e.g., 'Executive Summary', 'User Stories')")
class PlanPrdInput(ContractModel):
    document_title: str = Field(description="The title of the PRD document (e.g., 'Product Requirements Document: [Product Name]')")
    planning_notes: Optional[str] = Field(default=None, description='Any notes about the approach, assumptions, or special considerations for this PRD')
    product_name: str = Field(description='The name of the product or feature being documented')
    sections: list[PlanPrdInputSectionsItemModel] = Field(description='The sections to include in the PRD, in order', min_length=3, max_length=15)
    target_audience: Optional[str] = Field(default=None, description="Who this PRD is written for (e.g., 'Engineering team, Product stakeholders, Executive leadership')")
class WritePrdSectionInput(ContractModel):
    is_last_section: bool = Field(description='Set to true when this is the final section and the PRD is complete')
    markdown_content: str = Field(description='The markdown content for this section. Include proper heading (## or ###), formatted lists, tables if needed, and clear prose. Do NOT include the document title - only the section content.')
    operation: Literal['write', 'append'] = Field(description="Use 'write' for the first section (creates file), 'append' for subsequent sections")
    section_number: int = Field(description='The sequential number of this section (1, 2, 3, etc.)')
    section_title: str = Field(description="The title of this section (e.g., 'Executive Summary', 'Functional Requirements')")


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='plan_prd',
        description='Plan the PRD document structure before writing. Analyze the source content and create a structured plan for the document sections.',
        input_model=PlanPrdInput,
        terminates_run=False,
        metadata={'registry_name': 'plan_prd'},
    ),
    LocalToolSpec(
        name='write_prd_section',
        description="Write a section of the PRD to the markdown file. Use 'write' operation for the first section (creates file with title), 'append' for subsequent sections. Set is_last_section to true when you have written the final section.",
        input_model=WritePrdSectionInput,
        terminates_run=False,
        terminates_when='is_last_section',
        metadata={'registry_name': 'write_prd_section'},
    ),
)
