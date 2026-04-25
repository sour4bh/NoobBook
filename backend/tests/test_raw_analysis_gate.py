"""
NBB-203 gate tests: raw-code analysis must be disabled outside dev/single-user mode.

Verifies the pre-migration mitigation documented in
``docs/tickets/epics/NBB-002.md`` (#nbb-203) and the permanent-replacement
tracker in ``docs/tickets/DEFERRED.md`` D-002.

Gate requires BOTH:
    - ``NOOBBOOK_AUTH_REQUIRED=false``
    - ``NOOBBOOK_ALLOW_RAW_ANALYSIS=true``

Any other combination must refuse to execute model-written Python.

Import bootstrap note:
    ``app.services.integrations.supabase.__init__`` instantiates
    ``AuthService()`` at module load, which needs a Supabase client.
    We set dummy env vars and pre-replace the client singleton with a
    MagicMock before touching any ``app.*`` import. This only affects
    this test module and does not touch ``backend/config.py``
    (the known `app.config` vs `backend/config.py` collision is a
    separate structural follow-up — flag-not-fix per the ticket guardrail).
"""
import os
from unittest.mock import MagicMock, patch

import pytest

# Supabase env + singleton must be set BEFORE any `app.*` import. See
# module docstring for why.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    # JWT-shaped dummy; supabase-py validates structure on construct.
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0IiwiaWF0IjoxNzAwMDAwMDAwfQ."
    "dummy-signature-for-tests",
)

from app.services.integrations.supabase import supabase_client as _supabase_client  # noqa: E402

_supabase_client.SupabaseClient._instance = MagicMock()
_supabase_client.SupabaseClient._initialized = True

from app.sources.analysis.csv import run as analysis_executor_module  # noqa: E402
from app.sources.analysis.csv.run import (  # noqa: E402
    analysis_executor,
    raw_analysis_enabled,
    RAW_ANALYSIS_DISABLED_MESSAGE,
)
from app.sources.analysis.csv.agent import csv_analyzer_agent  # noqa: E402


AUTH_ENV = "NOOBBOOK_AUTH_REQUIRED"
ALLOW_ENV = "NOOBBOOK_ALLOW_RAW_ANALYSIS"


@pytest.fixture
def raw_analysis_clear_env(monkeypatch):
    """Start each test from an unset env so defaults apply (auth required, raw disabled)."""
    monkeypatch.delenv(AUTH_ENV, raising=False)
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    return monkeypatch


@pytest.fixture
def raw_analysis_enabled_env(monkeypatch):
    """Dev/single-user mode with explicit raw-code opt-in."""
    monkeypatch.setenv(AUTH_ENV, "false")
    monkeypatch.setenv(ALLOW_ENV, "true")
    return monkeypatch


# ---------------------------------------------------------------------------
# raw_analysis_enabled() matrix
# ---------------------------------------------------------------------------

def test_both_unset_defaults_to_disabled(raw_analysis_clear_env):
    assert raw_analysis_enabled() is False


def test_auth_required_unset_allow_true_is_disabled(raw_analysis_clear_env):
    raw_analysis_clear_env.setenv(ALLOW_ENV, "true")
    # AUTH_REQUIRED defaults to "true"
    assert raw_analysis_enabled() is False


def test_auth_false_allow_unset_is_disabled(raw_analysis_clear_env):
    raw_analysis_clear_env.setenv(AUTH_ENV, "false")
    # ALLOW defaults to "false"
    assert raw_analysis_enabled() is False


def test_auth_false_allow_false_is_disabled(raw_analysis_clear_env):
    raw_analysis_clear_env.setenv(AUTH_ENV, "false")
    raw_analysis_clear_env.setenv(ALLOW_ENV, "false")
    assert raw_analysis_enabled() is False


def test_auth_true_allow_true_is_disabled(raw_analysis_clear_env):
    raw_analysis_clear_env.setenv(AUTH_ENV, "true")
    raw_analysis_clear_env.setenv(ALLOW_ENV, "true")
    assert raw_analysis_enabled() is False


def test_auth_false_allow_true_is_enabled(raw_analysis_enabled_env):
    assert raw_analysis_enabled() is True


@pytest.mark.parametrize("value", ["1", "yes", "on", "TRUE", "True"])
def test_allow_raw_truthy_variants_enable(raw_analysis_clear_env, value):
    raw_analysis_clear_env.setenv(AUTH_ENV, "false")
    raw_analysis_clear_env.setenv(ALLOW_ENV, value)
    assert raw_analysis_enabled() is True


# ---------------------------------------------------------------------------
# analysis_executor.dispatch('run_analysis', ...) gate
# ---------------------------------------------------------------------------

def test_execute_tool_run_analysis_blocked_when_disabled(raw_analysis_clear_env):
    result, is_termination = analysis_executor.dispatch(
        "run_analysis",
        {"code": "result = 1 + 1"},
        "proj-1",
        "src-1",
    )
    assert is_termination is False
    assert result["success"] is False
    # Error names both env vars so users/grep can find the switch
    assert AUTH_ENV in result["error"]
    assert ALLOW_ENV in result["error"]
    assert "NBB-203" in result["error"] or "D-002" in result["error"]


def test_execute_tool_run_analysis_blocked_in_auth_required_mode(raw_analysis_clear_env):
    raw_analysis_clear_env.setenv(AUTH_ENV, "true")
    raw_analysis_clear_env.setenv(ALLOW_ENV, "true")
    result, _ = analysis_executor.dispatch(
        "run_analysis",
        {"code": "result = 42"},
        "proj-1",
        "src-1",
    )
    assert result["success"] is False
    assert result["error"] == RAW_ANALYSIS_DISABLED_MESSAGE


def test_execute_tool_does_not_reach_exec_when_disabled(raw_analysis_clear_env):
    # Prove the gate fires BEFORE _run_analysis runs.
    with patch.object(analysis_executor, "_run_analysis") as inner:
        result, _ = analysis_executor.dispatch(
            "run_analysis",
            {"code": "result = 1"},
            "proj-1",
            "src-1",
        )
    inner.assert_not_called()
    assert result["success"] is False


def test_return_analysis_tool_unaffected_by_gate(raw_analysis_clear_env):
    # return_analysis is the termination tool; it only echoes input. The gate
    # must NOT block it — otherwise the agent couldn't return a refusal or a
    # legitimate no-op result.
    result, is_termination = analysis_executor.dispatch(
        "return_analysis",
        {"summary": "done", "data": {}, "image_paths": []},
        "proj-1",
        "src-1",
    )
    assert is_termination is True
    assert result["summary"] == "done"


def test_execute_tool_run_analysis_runs_when_enabled(raw_analysis_enabled_env):
    # When enabled, the gate must pass and exec() should run a trivial snippet.
    # We stub out _load_dataframe so the test does not need Supabase.
    import pandas as pd

    with patch.object(
        analysis_executor,
        "_load_dataframe",
        return_value=pd.DataFrame({"x": [1, 2, 3]}),
    ):
        result, is_termination = analysis_executor.dispatch(
            "run_analysis",
            {"code": "result = int(df['x'].sum())"},
            "proj-1",
            "src-1",
        )

    assert is_termination is False
    assert result["success"] is True, result
    assert "6" in result["output"]


# ---------------------------------------------------------------------------
# csv_analyzer_agent.run early-exit gate
# ---------------------------------------------------------------------------

def test_csv_analyzer_agent_refuses_when_disabled_without_calling_claude(
    raw_analysis_clear_env,
):
    # Load-bearing assertion: Claude API is NEVER called when the gate is
    # closed, so production never burns cost trying to reach a blocked exec.
    with patch(
        "app.sources.analysis.csv.agent.claude_service.send_message"
    ) as send_message:
        result = csv_analyzer_agent.run(
            project_id="proj-1",
            source_id="src-1",
            query="what is the mean?",
        )

    send_message.assert_not_called()
    assert result["success"] is False
    assert result["error"] == RAW_ANALYSIS_DISABLED_MESSAGE
    assert result["usage"] == {"input_tokens": 0, "output_tokens": 0}


def test_csv_analyzer_agent_refuses_in_auth_required_mode_even_with_allow_true(
    raw_analysis_clear_env,
):
    raw_analysis_clear_env.setenv(AUTH_ENV, "true")
    raw_analysis_clear_env.setenv(ALLOW_ENV, "true")
    with patch(
        "app.sources.analysis.csv.agent.claude_service.send_message"
    ) as send_message:
        result = csv_analyzer_agent.run(
            project_id="proj-1",
            source_id="src-1",
            query="what is the mean?",
        )

    send_message.assert_not_called()
    assert result["success"] is False


def test_csv_analyzer_agent_refuses_when_allow_missing(raw_analysis_clear_env):
    raw_analysis_clear_env.setenv(AUTH_ENV, "false")
    # ALLOW intentionally unset
    with patch(
        "app.sources.analysis.csv.agent.claude_service.send_message"
    ) as send_message:
        result = csv_analyzer_agent.run(
            project_id="proj-1",
            source_id="src-1",
            query="what is the mean?",
        )

    send_message.assert_not_called()
    assert result["success"] is False


def test_disabled_message_constant_is_shared():
    # Prevent drift: agent and executor surface the same user-facing message.
    assert RAW_ANALYSIS_DISABLED_MESSAGE is analysis_executor_module.RAW_ANALYSIS_DISABLED_MESSAGE
