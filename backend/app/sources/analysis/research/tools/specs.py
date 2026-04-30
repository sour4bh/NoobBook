"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec, ToolSpec, provider_tool
from app.base.contracts import ContractModel


class TavilySearchAdvanceInput(ContractModel):
    chunks_per_source: Optional[int] = Field(default=None, description='Number of content chunks per source (default: 3)')
    include_domains: Optional[list[str]] = Field(default=None, description='Limit search to these domains only')
    include_raw_content: Optional[bool] = Field(default=None, description='Include raw page content in search results')
    max_results: Optional[int] = Field(default=None, description='Maximum number of search results (default: 5, max: 7)')
    query: Optional[str] = Field(default=None, description="Search query (required for type='search')")
    search_depth: Optional[Literal['basic', 'advanced']] = Field(default=None, description="Search/extract depth - use 'advanced' for comprehensive results")
    topic: Optional[Literal['general', 'news', 'finance']] = Field(default=None, description='Topic category for search (default: general)')
    type: Literal['search', 'extract'] = Field(description="Operation type: 'search' for web search, 'extract' for extracting content from URLs")
    urls: Optional[list[str]] = Field(default=None, description="List of URLs to extract content from (required for type='extract')")
class WriteResearchToFileInput(ContractModel):
    is_last_segment: bool = Field(description='Set to true when this is the final segment and research is complete')
    operation: Literal['write', 'append'] = Field(description="Use 'write' for the first segment (creates file), 'append' for subsequent segments")
    research_content: str = Field(description='The research content to write. Include inline citations as [Source: URL] immediately after the cited content. Format with clear headings using ## and ###. Ensure links are complete URLs and not broken across lines. Additionally inclide any data content that you already have knolwedge off, and if you want to add your own knowledge its good to search about it to also have valid citations')
    segment_number: int = Field(description='The sequential number of this research segment (1, 2, 3, etc.)')


TOOL_SPECS: tuple[ToolSpec, ...] = (
    LocalToolSpec(
        name='tavily_search_advance',
        description="Advanced Tavily tool for web search or URL content extraction. Use 'search' for researching topics, use 'extract' for getting content from specific URLs.",
        input_model=TavilySearchAdvanceInput,
        terminates_run=False,
        metadata={'registry_name': 'tavily_search_advance'},
    ),
    provider_tool(
        registry_name='web_search',
        name='web_search',
        provider_type='web_search_20250305',
        metadata={'max_uses': 10},
    ),
    LocalToolSpec(
        name='write_research_to_file',
        description="Write a research segment to the output file. Call this tool to save your research findings. You can write multiple segments - use 'write' for the first segment and 'append' for subsequent segments. Set is_last_segment to true when you have completed all research.",
        input_model=WriteResearchToFileInput,
        terminates_run=False,
        terminates_when='is_last_segment',
        metadata={'registry_name': 'write_research_to_file'},
    ),
)
