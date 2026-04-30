"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec, ToolSpec, provider_tool
from app.base.contracts import ContractModel


class ReturnSearchResultInput(ContractModel):
    content: str = Field(description='The main extracted content from the page. Should be clean, well-formatted text suitable for RAG processing. Include all relevant information from the page.')
    content_type: Optional[Literal['article', 'documentation', 'blog', 'news', 'product', 'other']] = Field(default=None, description='The type of content retrieved.')
    error_message: Optional[str] = Field(default=None, description='If success is false, describe why the search/fetch failed.')
    source_urls: Optional[list[str]] = Field(default=None, description='List of all source URLs that contributed to this result.')
    success: bool = Field(description='Whether the search/fetch was successful in retrieving useful content.')
    summary: Optional[str] = Field(default=None, description='A brief summary (2-3 sentences) of what the content is about.')
    title: Optional[str] = Field(default=None, description='Title of the page/content retrieved, or a descriptive title for search results.')
    url: Optional[str] = Field(default=None, description='The primary URL that was fetched or the most relevant URL from search results.')
class TavilySearchInput(ContractModel):
    query: str = Field(description='The search query. Should be the URL or topic you want to search for, try to mention the url as well as the topic')


TOOL_SPECS: tuple[ToolSpec, ...] = (
    LocalToolSpec(
        name='return_search_result',
        description='Call this tool when you have successfully gathered all information from the web search or URL fetch. This signals completion and returns the final structured result.',
        input_model=ReturnSearchResultInput,
        terminates_run=True,
        metadata={'registry_name': 'return_search_result'},
    ),
    LocalToolSpec(
        name='tavily_search',
        description='Search the web using Tavily AI. use in combinatioon with the web search tool to gather better information',
        input_model=TavilySearchInput,
        terminates_run=False,
        metadata={'registry_name': 'tavily_search'},
    ),
    provider_tool(
        registry_name='web_search',
        name='web_search',
        provider_type='web_search_20250305',
        metadata={'max_uses': 2},
    ),
)
