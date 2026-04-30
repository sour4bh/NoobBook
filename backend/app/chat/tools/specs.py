"""Typed tool specs for this domain-owned tool family."""

from typing import Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class SearchSourcesInput(ContractModel):
    keywords: Optional[list[str]] = Field(default=None, description="Optional keywords (1-2 words each) for fast text matching. Use for finding specific terms, names, concepts, or technical words. Example: ['microservices', 'API gateway', 'Redis']")
    query: Optional[str] = Field(default=None, description="Optional semantic search query phrase for finding conceptually related content. Use natural language questions or descriptive phrases. Example: 'What are the benefits of using a load balancer?'")
    source_id: str = Field(description='The ID of the SOURCE to search (from available sources in your context). This is NOT what you cite - the tool will return chunks with chunk_ids that you use for citations.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='search_sources',
        description="Search for information in the project's uploaded sources. Use this tool when the user asks questions that require information from their documents, PDFs, audio transcripts, or other uploaded content. IMPORTANT: You pass a source_id to search, but the tool returns CHUNKS with chunk_ids. Always cite using the chunk_id from results (format: source_page_chunk), NOT the source_id you passed in.",
        input_model=SearchSourcesInput,
        terminates_run=False,
        metadata={'registry_name': 'source_search_tool'},
    ),
)
