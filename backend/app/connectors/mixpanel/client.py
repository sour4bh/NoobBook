"""
Mixpanel Query API access for NoobBook chat.

Educational Note: Uses Mixpanel's Service Account auth (HTTP Basic) against
the Query API (https://mixpanel.com/api/query/). Credentials resolve through
the owning project/workspace with environment variables only as bootstrap
fallback.

The functions resolve credentials per call so each workspace can use its own
Mixpanel account.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

from app.config.secret import get_secret

logger = logging.getLogger(__name__)


REGION_HOSTS = {
    "us": "https://mixpanel.com",
    "eu": "https://eu.mixpanel.com",
    "in": "https://in.mixpanel.com",
}


def _resolve_config(
    project_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[HTTPBasicAuth], Optional[str]]:
    username = (
        get_secret("MIXPANEL_SERVICE_ACCOUNT_USERNAME", project_id=project_id)
        or ""
    ).strip().strip('"')
    secret = (
        get_secret("MIXPANEL_SERVICE_ACCOUNT_SECRET", project_id=project_id)
        or ""
    ).strip().strip('"')
    mixpanel_project_id = (
        get_secret("MIXPANEL_PROJECT_ID", project_id=project_id)
        or ""
    ).strip().strip('"')
    region = (
        get_secret("MIXPANEL_REGION", project_id=project_id)
        or "us"
    ).strip().lower() or "us"

    host = REGION_HOSTS.get(region, REGION_HOSTS["us"])
    base_url = f"{host}/api/query"
    auth = HTTPBasicAuth(username, secret) if username and secret else None
    return base_url, auth, mixpanel_project_id or None

def reload_config() -> None:
    """Compatibility hook; credentials are resolved per request."""


def is_configured(project_id: Optional[str] = None) -> bool:
    _base_url, auth, mixpanel_project_id = _resolve_config(project_id=project_id)
    return bool(auth and mixpanel_project_id)


def _make_request(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call the Mixpanel Query API.

    Educational Note: Mixpanel's Query API returns either JSON objects or
    NDJSON (for /export). The endpoints we use here all return JSON.
    """
    base_url, auth, mixpanel_project_id = _resolve_config(project_id=project_id)
    if not auth or not mixpanel_project_id:
        return {
            "success": False,
            "error": (
                "Mixpanel not configured. Please add MIXPANEL_SERVICE_ACCOUNT_USERNAME, "
                "MIXPANEL_SERVICE_ACCOUNT_SECRET, and MIXPANEL_PROJECT_ID in Workspace Settings."
            ),
        }

    # project_id is required on every Query API call
    merged_params = {"project_id": mixpanel_project_id}
    if params:
        merged_params.update({k: v for k, v in params.items() if v is not None})

    url = f"{base_url}/{endpoint.lstrip('/')}"
    headers = {"Accept": "application/json"}

    try:
        if method == "GET":
            response = requests.get(
                url, auth=auth, headers=headers, params=merged_params, timeout=30
            )
        elif method == "POST":
            response = requests.post(
                url, auth=auth, headers=headers, data=merged_params, timeout=30
            )
        else:
            return {"success": False, "error": f"Unsupported HTTP method: {method}"}

        if response.status_code == 200:
            try:
                return {"success": True, "data": response.json()}
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid JSON response from Mixpanel: {response.text[:200]}",
                }
        if response.status_code == 401:
            return {
                "success": False,
                "error": "Authentication failed. Check service account username/secret.",
            }
        if response.status_code == 402:
            return {
                "success": False,
                "error": "Mixpanel rejected the request (payment/quota). See response: "
                + response.text[:200],
            }
        if response.status_code == 403:
            return {
                "success": False,
                "error": "Permission denied. Service account must have access to the project.",
            }
        if response.status_code == 404:
            return {"success": False, "error": f"Not found: {endpoint}"}
        if response.status_code == 429:
            return {
                "success": False,
                "error": "Rate limit hit (Mixpanel Query API: 60/hr, 5 concurrent). Try again later.",
            }
        return {
            "success": False,
            "error": f"Mixpanel API error: {response.status_code} - {response.text[:200]}",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Mixpanel request timed out."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Could not connect to Mixpanel API."}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

# --- Tool methods ---

def list_events(
    limit: int = 100,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List event names tracked in the project.

    Endpoint: GET /events/names?type=general&limit=N
    """
    result = _make_request(
        "events/names",
        params={"type": "general", "limit": min(max(limit, 1), 255)},
        project_id=project_id,
    )
    if not result["success"]:
        return result

    names = result["data"]
    if not isinstance(names, list):
        names = []

    return {"success": True, "events": names, "total": len(names)}

def query_events(
    event_names: List[str],
    from_date: str,
    to_date: str,
    unit: str = "day",
    event_type: str = "general",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get event counts over time.

    Endpoint: GET /events?event=["A","B"]&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&unit=day&type=general
    """
    if not event_names:
        return {"success": False, "error": "event_names is required (non-empty list)."}
    if not from_date or not to_date:
        return {"success": False, "error": "from_date and to_date are required (YYYY-MM-DD)."}

    return _make_request(
        "events",
        params={
            "event": json.dumps(event_names),
            "from_date": from_date,
            "to_date": to_date,
            "unit": unit,
            "type": event_type,
        },
        project_id=project_id,
    )

def segmentation(
    event: str,
    from_date: str,
    to_date: str,
    on: Optional[str] = None,
    where: Optional[str] = None,
    unit: str = "day",
    segmentation_type: str = "general",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Segment a single event by a property.

    Endpoint: GET /segmentation?event=X&from_date=Y&to_date=Z&on=properties["..."]&type=general
    """
    if not event:
        return {"success": False, "error": "event is required."}
    if not from_date or not to_date:
        return {"success": False, "error": "from_date and to_date are required (YYYY-MM-DD)."}

    params: Dict[str, Any] = {
        "event": event,
        "from_date": from_date,
        "to_date": to_date,
        "unit": unit,
        "type": segmentation_type,
    }
    if on:
        params["on"] = on
    if where:
        params["where"] = where

    return _make_request(
        "segmentation",
        params=params,
        project_id=project_id,
    )

def list_funnels(project_id: Optional[str] = None) -> Dict[str, Any]:
    """List funnels configured in the project. Endpoint: GET /funnels/list"""
    result = _make_request("funnels/list", project_id=project_id)
    if not result["success"]:
        return result

    funnels = result["data"]
    if not isinstance(funnels, list):
        funnels = []

    formatted = [
        {"funnel_id": f.get("funnel_id"), "name": f.get("name")}
        for f in funnels
    ]
    return {"success": True, "funnels": formatted, "total": len(formatted)}

def query_funnel(
    funnel_id: int,
    from_date: str,
    to_date: str,
    unit: str = "day",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query funnel conversion over time.

    Endpoint: GET /funnels?funnel_id=N&from_date=Y&to_date=Z&unit=day
    """
    if funnel_id is None:
        return {"success": False, "error": "funnel_id is required (integer)."}
    if not from_date or not to_date:
        return {"success": False, "error": "from_date and to_date are required (YYYY-MM-DD)."}

    return _make_request(
        "funnels",
        params={
            "funnel_id": funnel_id,
            "from_date": from_date,
            "to_date": to_date,
            "unit": unit,
        },
        project_id=project_id,
    )

def retention(
    born_event: str,
    event: Optional[str],
    from_date: str,
    to_date: str,
    retention_type: str = "birth",
    unit: str = "day",
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retention analysis.

    Endpoint: GET /retention?from_date=Y&to_date=Z&retention_type=birth&born_event=X&event=Y&unit=day
    """
    if not born_event:
        return {"success": False, "error": "born_event is required."}
    if not from_date or not to_date:
        return {"success": False, "error": "from_date and to_date are required (YYYY-MM-DD)."}

    params: Dict[str, Any] = {
        "from_date": from_date,
        "to_date": to_date,
        "retention_type": retention_type,
        "born_event": born_event,
        "unit": unit,
    }
    if event:
        params["event"] = event

    return _make_request(
        "retention",
        params=params,
        project_id=project_id,
    )

def jql(
    script: str,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run a JQL script.

    Endpoint: POST /jql  (form-encoded with `script`)

    Educational Note: JQL is feature-complete but deprecated in Mixpanel's
    docs. Still the most expressive query tool — kept as an escape hatch.
    """
    if not script or not script.strip():
        return {"success": False, "error": "script is required (JavaScript JQL code)."}

    return _make_request(
        "jql",
        params={"script": script},
        method="POST",
        project_id=project_id,
    )
