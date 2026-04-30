"""Typed tool specs for this domain-owned tool family."""

from typing import Optional

from pydantic import Field

from app.agents.runtime.tool import LocalToolSpec
from app.base.contracts import ContractModel


class JiraGetIssueInput(ContractModel):
    include_comments: Optional[bool] = Field(default=None, description='Whether to include comments on the issue (default: true, limited to 10 most recent)')
    issue_key: str = Field(description="The Jira issue key (e.g., 'PROJ-123', 'ENG-456')")
class JiraGetProjectInput(ContractModel):
    project_key: str = Field(description="The Jira project key (e.g., 'PROJ', 'ENG', 'SALES')")
class JiraListProjectsInput(ContractModel):
    limit: Optional[int] = Field(default=None, description='Maximum number of projects to return (default: 50)')
    search_query: Optional[str] = Field(default=None, description='Optional search query to filter projects by name or key')
class JiraSearchIssuesInput(ContractModel):
    assignee: Optional[str] = Field(default=None, description='Filter by assignee username')
    issue_type: Optional[str] = Field(default=None, description="Filter by issue type (e.g., 'Bug', 'Story', 'Task', 'Epic')")
    jql: Optional[str] = Field(default=None, description="Custom JQL query string. If provided, overrides all other filter parameters. Example: 'project = PROJ AND status = Open'")
    max_results: Optional[int] = Field(default=None, description='Maximum number of issues to return (default: 50, max: 100)')
    project_key: Optional[str] = Field(default=None, description="Filter by project key (e.g., 'PROJ', 'ENG'). Optional but recommended to narrow results.")
    status: Optional[str] = Field(default=None, description="Filter by issue status (e.g., 'Open', 'In Progress', 'Done')")


TOOL_SPECS: tuple[LocalToolSpec, ...] = (
    LocalToolSpec(
        name='jira_get_issue',
        description='Get detailed information about a specific Jira issue by its key. Returns full issue details including description, status, assignee, reporter, priority, dates, and recent comments. Use this after finding issues with jira_search_issues to get complete information.',
        input_model=JiraGetIssueInput,
        terminates_run=False,
        metadata={'registry_name': 'jira_get_issue'},
    ),
    LocalToolSpec(
        name='jira_get_project',
        description='Get detailed information about a specific Jira project by its key. Returns project metadata including name, description, lead, project type, and available issue types. Use this after listing projects to understand project structure before searching for issues.',
        input_model=JiraGetProjectInput,
        terminates_run=False,
        metadata={'registry_name': 'jira_get_project'},
    ),
    LocalToolSpec(
        name='jira_list_projects',
        description='List all Jira projects that the user has access to. Use this to discover what projects exist before searching for issues. Returns project keys, names, and descriptions.',
        input_model=JiraListProjectsInput,
        terminates_run=False,
        metadata={'registry_name': 'jira_list_projects'},
    ),
    LocalToolSpec(
        name='jira_search_issues',
        description='Search for Jira issues using filters or JQL (Jira Query Language). Returns issue summaries with key, status, type, assignee, and other metadata. Use this after discovering available projects with jira_list_projects. For detailed information about a specific issue, use jira_get_issue.',
        input_model=JiraSearchIssuesInput,
        terminates_run=False,
        metadata={'registry_name': 'jira_search_issues'},
    ),
)
