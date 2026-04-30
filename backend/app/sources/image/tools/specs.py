"""Typed tool specs for this domain-owned tool family."""

from typing import Literal

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class SubmitImageExtractionInput(ContractModel):
    colors_and_style: str = Field(description='Description of color palette, visual style, design aesthetic, branding elements if any.')
    content_type: Literal['document', 'screenshot', 'diagram', 'chart', 'photo', 'infographic', 'table', 'handwriting', 'artwork', 'mixed', 'other'] = Field(description='The primary type of content in this image.')
    data_content: str = Field(description='If the image contains charts, graphs, tables, or infographics - extract the actual data, values, labels, trends, and key insights. Use [NO DATA] if not applicable.')
    subject: str = Field(description='What is this image about? The main subject, topic, or purpose of the image.')
    summary: str = Field(description='A comprehensive 2-3 sentence summary capturing the key information and purpose of this image.')
    text_content: str = Field(description='All visible text extracted from the image. Include headers, labels, captions, body text, annotations, etc. Preserve structure where possible. Use [NO TEXT] if no readable text exists.')
    visual_description: str = Field(description='Detailed description of visual elements: layout, composition, objects, people, scenes, illustrations, icons, and any non-text visual content.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='submit_image_extraction',
        description='Submit comprehensive extraction of content from an image. Analyze and describe all aspects of the image including text, visuals, data, and meaning.',
        input_model=SubmitImageExtractionInput,
        terminates_run=True,
        metadata={'registry_name': 'image_extraction'},
    ),
)
