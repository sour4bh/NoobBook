"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class ReadSourceContentInput(ContractModel):
    source_id: str = Field(description='The ID of the source to read content from')
    start_chunk: Optional[int] = Field(default=None, description='For large sources, which chunk to start reading from (1-indexed). Omit or use 1 for first batch. The tool response tells you the next start_chunk value.')
class WriteScriptSectionInput(ContractModel):
    is_final: bool = Field(description='Set to true when this is the final section and the script is complete')
    operation: Literal['write', 'append'] = Field(description="Use 'write' for the first section (creates file), 'append' for subsequent sections")
    script_content: str = Field(description='The script content to write. Write in a conversational tone optimized for text-to-speech. Avoid abbreviations, special characters, and bullet points. Use natural transitions between topics.')
    section_number: int = Field(description='The sequential number of this script section (1, 2, 3, etc.)')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='read_source_content',
        description='Read content from a source. For small sources (under 2000 tokens), returns full content. For larger sources, returns 5 chunks at a time. Use start_chunk to get the next batch. The tool tells you the next start_chunk value.',
        input_model=ReadSourceContentInput,
        terminates_run=False,
        metadata={'registry_name': 'read_source_content'},
    ),
    LocalToolSpec(
        name='write_script_section',
        description="Write a section of the audio script to the output file. Use 'write' for the first section (creates file), 'append' for subsequent sections. Set is_final to true when the script is complete.",
        input_model=WriteScriptSectionInput,
        terminates_run=False,
        terminates_when='is_final',
        metadata={'registry_name': 'write_script_section'},
    ),
)
