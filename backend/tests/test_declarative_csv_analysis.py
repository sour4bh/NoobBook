"""NBB-907 tests for safe declarative CSV analysis."""

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)

from app.providers.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client._client = MagicMock()
_supabase_client._initialized = True

from app.sources.analysis.csv.run import analysis_executor  # noqa: E402
from app.sources.analysis.csv.agent import csv_analyzer_agent  # noqa: E402


@pytest.fixture
def dataframe():
    return pd.DataFrame(
        {
            "region": ["west", "west", "east"],
            "revenue": [10, 15, 7],
            "orders": [2, 3, 1],
        }
    )


def run_with_df(request, dataframe):
    with patch.object(analysis_executor, "_load_dataframe", return_value=dataframe):
        return analysis_executor.dispatch("run_analysis", request, "proj-1", "src-1")


def test_inspect_returns_columns_and_preview(dataframe):
    result, is_termination = run_with_df(
        {"operation": {"kind": "inspect", "limit": 2}},
        dataframe,
    )

    assert is_termination is False
    assert result["success"] is True
    assert result["data"]["columns"] == ["region", "revenue", "orders"]
    assert result["data"]["rows"] == 3
    assert len(result["data"]["preview"]) == 2


def test_filter_sort_and_limit(dataframe):
    result, _ = run_with_df(
        {
            "operations": [
                {"kind": "filter", "filters": [{"column": "region", "operator": "eq", "value": "west"}]},
                {"kind": "sort", "sort": [{"column": "revenue", "direction": "desc"}], "limit": 1},
            ]
        },
        dataframe,
    )

    assert result["success"] is True
    assert result["data"] == [{"region": "west", "revenue": 15, "orders": 3}]


def test_aggregate_groups_metrics(dataframe):
    result, _ = run_with_df(
        {
            "operation": {
                "kind": "aggregate",
                "group_by": ["region"],
                "metrics": [
                    {"column": "revenue", "function": "sum", "name": "total_revenue"},
                    {"function": "count", "name": "row_count"},
                ],
                "sort": [{"column": "total_revenue", "direction": "desc"}],
            }
        },
        dataframe,
    )

    assert result["success"] is True
    assert result["data"][0] == {"region": "west", "total_revenue": 25, "row_count": 2}


def test_invalid_request_fails_closed(dataframe):
    result, _ = run_with_df({"code": "result = df.revenue.sum()"}, dataframe)

    assert result["success"] is False
    assert "Invalid analysis request" in result["error"]


def test_unknown_column_fails_closed(dataframe):
    result, _ = run_with_df(
        {"operation": {"kind": "filter", "filters": [{"column": "missing", "operator": "eq", "value": 1}]}},
        dataframe,
    )

    assert result["success"] is False
    assert "Unknown column" in result["error"]


def test_chart_uploads_image(dataframe):
    with patch.object(analysis_executor, "_load_dataframe", return_value=dataframe), patch(
        "app.sources.analysis.csv.run.storage_service.upload_ai_image",
        return_value=True,
    ) as upload:
        result, _ = analysis_executor.dispatch(
            "run_analysis",
            {"operation": {"kind": "chart", "chart_type": "bar", "x": "region", "y": "revenue"}},
            "proj-1",
            "src-1",
        )

    assert result["success"] is True
    assert result["plot_filenames"][0].startswith("src-1_plot_")
    upload.assert_called_once()


def test_return_analysis_tool_still_terminates():
    result, is_termination = analysis_executor.dispatch(
        "return_analysis",
        {"summary": "done", "data": {}, "image_paths": []},
        "proj-1",
        "src-1",
    )

    assert is_termination is True
    assert result["summary"] == "done"


def test_csv_analyzer_calls_claude_without_raw_gate():
    with patch.object(
        csv_analyzer_agent,
        "_load_config",
        return_value={
            "system_prompt": "Analyze CSV data.",
            "user_message": "Analyze {filename}: {query}",
            "model": "claude-3-haiku-20240307",
            "max_tokens": 100,
            "temperature": 0,
        },
    ), patch.object(
        csv_analyzer_agent,
        "_load_tools",
        return_value=[],
    ), patch("app.sources.analysis.csv.agent.claude_service.send_message") as send_message:
        send_message.return_value = {
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "content_blocks": [],
            "stop_reason": "end_turn",
        }
        result = csv_analyzer_agent.run(
            project_id="proj-1",
            source_id="src-1",
            query="what is the mean?",
        )

    send_message.assert_called()
    assert result["success"] is False
