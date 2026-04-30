"""Typed tool specs for this domain-owned tool family."""

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class SubmitSlideExtractionInput(ContractModel):
    layout_notes: str = Field(description='Notable layout observations: visual hierarchy, color emphasis, positioning of elements, design patterns. Brief observations only.')
    slide_number: int = Field(description='The exact slide number as specified in the user message. Use the slide numbers provided, not 1, 2, 3.')
    slide_title: str = Field(description='The main title or heading of the slide. If no title exists, use [NO TITLE].')
    text_content: str = Field(description='All text content from the slide including bullet points, paragraphs, labels, captions, and any other text. Preserve the structure with line breaks. If no text, use [NO TEXT CONTENT].')
    visual_elements: str = Field(description='Description of all visual elements: charts (type, data shown, trends), images (what they depict), diagrams (structure, flow), icons, shapes. If no visuals, use [NO VISUAL ELEMENTS].')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='submit_slide_extraction',
        description='Submit extracted content for a single presentation slide. Call this tool ONCE for EACH slide you are given. Use the exact slide numbers provided in the user message. Each extraction should capture all visual and textual content from the slide, made self-contained with context from surrounding slides if needed.',
        input_model=SubmitSlideExtractionInput,
        terminates_run=True,
        metadata={'registry_name': 'pptx_extraction'},
    ),
)
