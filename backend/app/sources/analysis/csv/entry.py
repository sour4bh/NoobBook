"""Chat-facing entrypoint for the CSV analyzer source tool."""

from typing import Any, Dict, Optional

from app.sources.analysis.csv.agent import csv_analyzer_agent


def execute(
    project_id: str,
    source_id: str,
    query: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute CSV analyzer agent for a user query.

    Args:
        project_id: Project ID for file paths and cost tracking
        source_id: Source ID of the CSV file to analyze
        query: User's question about the CSV data

    Returns:
        Dict with analysis result or error
    """
    if not source_id:
        return {
            "success": False,
            "error": "source_id is required"
        }

    if not query:
        return {
            "success": False,
            "error": "query is required"
        }

    result = csv_analyzer_agent.run(
        project_id=project_id,
        source_id=source_id,
        query=query,
        chat_id=chat_id,
        user_id=user_id,
    )

    if result.get("success"):
        response = {
            "success": True,
            "content": result.get("summary", "No analysis result"),
            "data": result.get("data"),
            "iterations": result.get("iterations", 0)
        }

        # Include image paths if any plots were generated
        if result.get("image_paths"):
            response["image_paths"] = result["image_paths"]

        return response
    else:
        return {
            "success": False,
            "error": result.get("error", "Analysis failed")
        }
