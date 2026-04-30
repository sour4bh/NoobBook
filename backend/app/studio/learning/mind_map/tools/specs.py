"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class GenerateMindMapInputNodesItemModel(ContractModel):
    description: str = Field(description='Brief explanation of this concept (1-2 sentences, max 50 words)')
    id: str = Field(description="Unique identifier for this node (e.g., 'node_1', 'node_2')")
    label: str = Field(description='Short display label for the node (max 5 words)')
    node_type: Literal['root', 'category', 'leaf'] = Field(description='root=main topic (only 1), category=grouping/subtopic, leaf=specific detail/fact')
    parent_id: Optional[str] = Field(description='ID of parent node. Must be null for root node only. All other nodes must reference an existing node.')
class GenerateMindMapInput(ContractModel):
    nodes: list[GenerateMindMapInputNodesItemModel] = Field(description='Array of mind map nodes forming a tree structure. First node must be the root (parent_id: null).', min_length=5, max_length=150)
    topic_summary: str = Field(description='A brief 1-2 sentence summary of what this mind map covers')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='generate_mind_map',
        description='Submit a hierarchical mind map structure representing the key concepts and their relationships from the content.',
        input_model=GenerateMindMapInput,
        terminates_run=True,
        metadata={'registry_name': 'mind_map_tool'},
    ),
)
