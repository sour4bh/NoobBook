"""Typed tool specs for this domain-owned tool family."""

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class SubmitPageExtractionInput(ContractModel):
    extracted_text: str = Field(description='The complete extracted text from this page. Make it self-contained: if this page has content that belongs under a heading/section from a previous page, prepend that heading. If a sentence starts on a previous page, include enough context. If no readable text exists, use [NO TEXT CONTENT].')
    page_number: int = Field(description='The exact page number as specified in the user message. Use the page numbers provided, not 1, 2, 3.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='submit_page_extraction',
        description='Submit extracted text for a single PDF page. Call this tool ONCE for EACH page you are given. You must use the exact page numbers provided in the user message. Each extraction should be self-contained - if content on this page continues from a previous page (like bullet points under a heading from an earlier page), include that heading/context at the start so the extraction makes sense on its own.',
        input_model=SubmitPageExtractionInput,
        terminates_run=True,
        metadata={'registry_name': 'pdf_extraction'},
    ),
)
