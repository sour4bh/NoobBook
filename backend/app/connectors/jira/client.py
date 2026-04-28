"""
Jira API integration for NoobBook.

Educational Note: This module provides functions to query Jira projects and issues
using the Jira REST API v3. Credentials resolve through the owning
project/workspace with environment variables only as bootstrap fallback.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
import requests
from requests.auth import HTTPBasicAuth

from app.config.secret import get_secret

logger = logging.getLogger(__name__)


def _resolve_config(
    project_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[HTTPBasicAuth], Optional[str]]:
    """
    Resolve Jira configuration for a project/workspace.

    Educational Note: Supports both old and new Jira API formats:
    - Old: https://your-company.atlassian.net/rest/api/3
    - New: https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3

    If JIRA_CLOUD_ID is provided, uses the new centralized gateway format.
    Otherwise, falls back to the legacy direct domain format.
    """
    jira_domain = (get_secret('JIRA_DOMAIN', project_id=project_id) or '').rstrip('/')
    jira_email = get_secret('JIRA_EMAIL', project_id=project_id)
    jira_api_key = (get_secret('JIRA_API_KEY', project_id=project_id) or '').strip('"')
    jira_cloud_id = (get_secret('JIRA_CLOUD_ID', project_id=project_id) or '').strip()

    # Determine base URL format
    if jira_cloud_id:
        # New centralized gateway format (API tokens with scopes)
        base_url = f"https://api.atlassian.com/ex/jira/{jira_cloud_id}/rest/api/3"
        config_label = f"Atlassian API Gateway (Cloud ID: {jira_cloud_id[:8]}...)"
    elif jira_domain:
        # Legacy direct domain format (old API tokens)
        if not jira_domain.startswith('http'):
            jira_domain = f"https://{jira_domain}"
        base_url = f"{jira_domain}/rest/api/3"
        config_label = jira_domain
    else:
        base_url = None
        config_label = None

    # Auth remains the same for both formats (Basic Auth with email + token)
    auth = HTTPBasicAuth(jira_email, jira_api_key) if jira_email and jira_api_key else None
    return base_url, auth, config_label


def reload_config() -> None:
    """Compatibility hook; credentials are resolved per request."""


def is_configured(project_id: Optional[str] = None) -> bool:
    """Check if Jira credentials are configured."""
    base_url, auth, _label = _resolve_config(project_id=project_id)
    return bool(base_url and auth)


def _make_request(
    endpoint: str,
    method: str = 'GET',
    params: Optional[Dict] = None,
    json_data: Optional[Dict] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Make a request to the Jira API.

    Args:
        endpoint: API endpoint (relative to base_url)
        method: HTTP method (GET or POST)
        params: Query parameters
        json_data: JSON body for POST requests

    Returns:
        Dict with 'success' flag and either 'data' or 'error'
    """
    base_url, auth, config_label = _resolve_config(project_id=project_id)
    if not base_url or not auth:
        return {
            "success": False,
            "error": "Jira not configured. Please add JIRA_EMAIL, JIRA_API_KEY, and either JIRA_CLOUD_ID or JIRA_DOMAIN in Workspace Settings."
        }
    logger.debug("Jira request using configuration: %s", config_label)

    try:
        url = f"{base_url}/{endpoint}"
        headers = {'Accept': 'application/json'}

        if method == 'GET':
            response = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
        elif method == 'POST':
            headers['Content-Type'] = 'application/json'
            response = requests.post(url, auth=auth, headers=headers, json=json_data, timeout=30)
        else:
            return {"success": False, "error": f"Unsupported HTTP method: {method}"}

        # Handle response codes
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        elif response.status_code == 401:
            return {"success": False, "error": "Authentication failed. Check your JIRA_EMAIL and JIRA_API_KEY"}
        elif response.status_code == 403:
            return {"success": False, "error": "Permission denied. Check your Jira permissions"}
        elif response.status_code == 404:
            return {"success": False, "error": f"Not found: {endpoint}"}
        elif response.status_code == 410:
            return {"success": False, "error": f"API endpoint deprecated: {endpoint}"}
        else:
            return {
                "success": False,
                "error": f"Jira API error: {response.status_code} - {response.text[:200]}"
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timed out. Jira server might be slow or unreachable"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection failed. Check JIRA_DOMAIN and network connectivity"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

def list_projects(
    search_query: Optional[str] = None,
    limit: int = 50,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List Jira projects.

    Args:
        search_query: Optional search query to filter projects
        limit: Maximum number of projects to return (default: 50)

    Returns:
        Dict with 'success' flag and either 'projects' list or 'error'
    """
    if search_query:
        # Use project search endpoint
        result = _make_request(
            'project/search',
            params={'query': search_query, 'maxResults': limit},
            project_id=project_id,
        )
        if not result['success']:
            return result

        projects = result['data'].get('values', [])
    else:
        # Get all projects
        result = _make_request(
            'project',
            params={'maxResults': limit},
            project_id=project_id,
        )
        if not result['success']:
            return result

        data = result['data']
        projects = data if isinstance(data, list) else data.get('values', [])

    # Format project data
    formatted_projects = []
    for project in projects[:limit]:
        formatted_projects.append({
            'key': project.get('key'),
            'name': project.get('name'),
            'description': project.get('description', ''),
            'projectTypeKey': project.get('projectTypeKey'),
            'lead': project.get('lead', {}).get('displayName') if 'lead' in project else None
        })

    return {
        "success": True,
        "projects": formatted_projects,
        "total": len(formatted_projects)
    }

def get_project(
    project_key: str,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific project.

    Args:
        project_key: Jira project key (e.g., 'PROJ', 'ENG')

    Returns:
        Dict with 'success' flag and either 'project' dict or 'error'
    """
    if not project_key:
        return {"success": False, "error": "project_key is required"}

    result = _make_request(f'project/{project_key}', project_id=project_id)
    if not result['success']:
        return result

    project = result['data']

    # Format detailed project data
    return {
        "success": True,
        "project": {
            'key': project.get('key'),
            'name': project.get('name'),
            'description': project.get('description', ''),
            'lead': project.get('lead', {}).get('displayName') if 'lead' in project else None,
            'projectTypeKey': project.get('projectTypeKey'),
            'issueTypes': [t.get('name') for t in project.get('issueTypes', [])]
        }
    }

def search_issues(
    project_key: Optional[str] = None,
    jql: Optional[str] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    issue_type: Optional[str] = None,
    max_results: int = 50,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for Jira issues using JQL or filters.

    Educational Note: Uses Jira's enhanced JQL search API (POST /search/jql)
    which supports pagination and is the recommended endpoint.

    Args:
        project_key: Filter by project (optional)
        jql: Custom JQL query (overrides other filters if provided)
        status: Filter by status (e.g., 'Open', 'In Progress')
        assignee: Filter by assignee username
        issue_type: Filter by issue type (e.g., 'Bug', 'Story')
        max_results: Maximum results to return (default: 50, max: 100)

    Returns:
        Dict with 'success' flag and either 'issues' list or 'error'
    """
    # Cap max_results
    # TODO: Add pagination support to fetch beyond the first page of results
    max_results = min(max_results, 100)

    # Build JQL query if not provided
    if not jql:
        jql_parts = []

        if project_key:
            jql_parts.append(f'project = "{project_key}"')
        if status:
            jql_parts.append(f'status = "{status}"')
        if assignee:
            jql_parts.append(f'assignee = "{assignee}"')
        if issue_type:
            jql_parts.append(f'type = "{issue_type}"')

        jql = ' AND '.join(jql_parts) if jql_parts else 'ORDER BY created DESC'

    # Define fields to retrieve
    fields = [
        'summary', 'status', 'assignee', 'reporter', 'created',
        'updated', 'priority', 'issuetype', 'description'
    ]

    # Build payload for enhanced JQL endpoint
    payload = {
        'jql': jql,
        'fields': fields,
        'maxResults': max_results
    }


    # Use enhanced JQL endpoint
    result = _make_request(
        'search/jql',
        method='POST',
        json_data=payload,
        project_id=project_id,
    )
    if not result['success']:
        return result

    # Format issue data
    data = result['data']
    issues = []

    for issue in data.get('issues', []):
        fields_data = issue.get('fields', {})
        issues.append({
            'key': issue.get('key'),
            'summary': fields_data.get('summary'),
            'status': fields_data.get('status', {}).get('name'),
            'type': fields_data.get('issuetype', {}).get('name'),
            'priority': fields_data.get('priority', {}).get('name') if fields_data.get('priority') else None,
            'assignee': fields_data.get('assignee', {}).get('displayName') if fields_data.get('assignee') else 'Unassigned',
            'reporter': fields_data.get('reporter', {}).get('displayName') if fields_data.get('reporter') else 'Unknown',
            'created': fields_data.get('created'),
            'updated': fields_data.get('updated')
        })

    return {
        "success": True,
        "issues": issues,
        "total": len(issues),
        "jql": jql
    }

def get_issue(
    issue_key: str,
    include_comments: bool = True,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific issue.

    Args:
        issue_key: Jira issue key (e.g., 'PROJ-123')
        include_comments: Whether to include comments (default: True)

    Returns:
        Dict with 'success' flag and either 'issue' dict or 'error'
    """
    if not issue_key:
        return {"success": False, "error": "issue_key is required"}

    # Get issue details
    result = _make_request(f'issue/{issue_key}', project_id=project_id)
    if not result['success']:
        return result

    issue = result['data']
    fields = issue.get('fields', {})

    # Format description (handle Atlassian Document Format rich text)
    # Limitation: Only extracts text from paragraph > text nodes.
    # Other ADF node types (headings, lists, tables, code blocks, media, etc.)
    # are silently dropped. Expand this if richer extraction is needed.
    description = fields.get('description')
    if isinstance(description, dict):
        content = description.get('content', [])
        text_parts = []
        for block in content:
            if block.get('type') == 'paragraph':
                for item in block.get('content', []):
                    if item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
        description = ' '.join(text_parts)

    issue_data = {
        'key': issue.get('key'),
        'summary': fields.get('summary'),
        'description': description or '',
        'status': fields.get('status', {}).get('name'),
        'type': fields.get('issuetype', {}).get('name'),
        'priority': fields.get('priority', {}).get('name') if fields.get('priority') else None,
        'assignee': fields.get('assignee', {}).get('displayName') if fields.get('assignee') else 'Unassigned',
        'reporter': fields.get('reporter', {}).get('displayName') if fields.get('reporter') else 'Unknown',
        'created': fields.get('created'),
        'updated': fields.get('updated'),
        'project': {
            'key': fields.get('project', {}).get('key'),
            'name': fields.get('project', {}).get('name')
        }
    }

    # Get comments if requested
    if include_comments:
        comments_result = _make_request(
            f'issue/{issue_key}/comment',
            project_id=project_id,
        )

        if comments_result['success']:
            comments = comments_result['data'].get('comments', [])[:10]  # Limit to 10 comments
            formatted_comments = []

            for comment in comments:
                body = comment.get('body', '')
                # Handle ADF rich text format (same paragraph > text limitation as above)
                if isinstance(body, dict):
                    content = body.get('content', [])
                    text_parts = []
                    for block in content:
                        if block.get('type') == 'paragraph':
                            for item in block.get('content', []):
                                if item.get('type') == 'text':
                                    text_parts.append(item.get('text', ''))
                    body = ' '.join(text_parts)

                formatted_comments.append({
                    'author': comment.get('author', {}).get('displayName', 'Unknown'),
                    'created': comment.get('created'),
                    'body': body
                })

            issue_data['comments'] = formatted_comments
            issue_data['comments_count'] = len(comments_result['data'].get('comments', []))

    return {
        "success": True,
        "issue": issue_data
    }
