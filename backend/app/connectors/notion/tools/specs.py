"""Typed tool specs for this domain-owned tool family."""

from typing import Literal, Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class NotionGetDatabaseSchemaInput(ContractModel):
    database_id: str = Field(description='The Notion database ID (32-character hex string or UUID format)')
class NotionQueryDatabaseInput(ContractModel):
    database_id: str = Field(description='The Notion database ID (32-character hex string or UUID format)')
    filter_json: Optional[str] = Field(default=None, description='Optional JSON object string using the Notion API filter format. Example: {"property": "Status", "select": {"equals": "Done"}}. Omit to return all pages.')
    limit: Optional[int] = Field(default=None, description='Maximum number of pages to return (default: 20, max: 100)')
class NotionReadPageInput(ContractModel):
    page_id: str = Field(description='The Notion page ID (32-character hex string or UUID format)')
class NotionSearchInput(ContractModel):
    filter_type: Optional[Literal['page', 'database']] = Field(default=None, description="Filter results by type: 'page' for pages only, 'database' for databases only. Omit to return both.")
    limit: Optional[int] = Field(default=None, description='Maximum number of results to return (default: 20, max: 100)')
    query: Optional[str] = Field(default=None, description='Search query string. If not provided, returns all accessible pages and databases.')


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='notion_get_database_schema',
        description='Get the schema (structure) of a Notion database including all properties and their types. Use this to understand the database structure before querying it. Returns property names and types (title, text, number, select, multi_select, date, checkbox, etc.).',
        input_model=NotionGetDatabaseSchemaInput,
        terminates_run=False,
        metadata={'registry_name': 'notion_get_database_schema'},
    ),
    LocalToolSpec(
        name='notion_query_database',
        description="Query a Notion database to retrieve pages (rows) with optional filtering. Returns pages with their property values. Use notion_get_database_schema first to understand available properties. For complex filters, pass filter_json as a JSON object string using Notion's filter format.",
        input_model=NotionQueryDatabaseInput,
        terminates_run=False,
        metadata={'registry_name': 'notion_query_database'},
    ),
    LocalToolSpec(
        name='notion_read_page',
        description="Read the full content of a specific Notion page. Returns the page's text content extracted from all blocks. Use this after finding a page ID via notion_search.",
        input_model=NotionReadPageInput,
        terminates_run=False,
        metadata={'registry_name': 'notion_read_page'},
    ),
    LocalToolSpec(
        name='notion_search',
        description='Search across all Notion pages and databases that the integration has access to. Returns basic information about matching pages and databases. Use this to discover what content exists before reading specific pages or querying databases.',
        input_model=NotionSearchInput,
        terminates_run=False,
        metadata={'registry_name': 'notion_search'},
    ),
)
