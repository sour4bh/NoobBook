"""
Focused runtime-boundary regression: ``claude_service.send_message`` must make
missing ``project_id`` observable so the pre-migration taste-audit fix in
NBB-109 cannot silently regress.

The full provider-neutral cost math has its own suite in ``test_cost_tracking.py``.
This file only proves the raw provider call still:

1. logs a warning when ``project_id`` is falsy so broken call sites are
   greppable in production logs, and
2. does not persist costs itself. Runtime wrappers own cost persistence.

Both the network call and the ``anthropic.Anthropic`` client are stubbed out
so the test does not depend on ANTHROPIC_API_KEY.
"""
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sys

from app.providers.anthropic.messages import ClaudeService

# The package ``__init__`` re-exports the singleton under the name
# ``claude_service``, which shadows the module binding on the parent package.
# Pull the underlying module out of ``sys.modules`` to reach its logger.
_CLAUDE_MODULE = sys.modules["app.providers.anthropic.messages"]
_CLAUDE_LOGGER_NAME = _CLAUDE_MODULE.logger.name


def _fake_anthropic_response():
    """Build a minimal object matching what ClaudeService.send_message reads."""
    return SimpleNamespace(
        content=[],
        model="claude-sonnet-4-5-20250929",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        stop_reason="end_turn",
    )


@pytest.fixture
def isolated_service(monkeypatch):
    """Fresh ClaudeService with API + spending-limit side effects stubbed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    service = ClaudeService()

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _fake_anthropic_response())
    )

    with patch.object(service, "_get_client", return_value=fake_client), patch(
        "app.providers.anthropic.messages.check_user_spending_limit",
        return_value=None,
    ):
        yield service


def test_send_message_without_project_id_logs_warning(isolated_service, caplog):
    """Missing project_id must produce a WARNING record mentioning project_id."""
    with caplog.at_level(logging.WARNING, logger=_CLAUDE_LOGGER_NAME):
        isolated_service.send_message(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5-20250929",
        )

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any("project_id" in rec.getMessage() for rec in warnings), (
        f"expected a warning mentioning project_id, got: {[r.getMessage() for r in warnings]}"
    )


def test_send_message_with_project_id_does_not_warn(isolated_service, caplog):
    """Runtime, not the raw Claude client, records costs after provider calls."""
    with caplog.at_level(logging.WARNING, logger=_CLAUDE_LOGGER_NAME):
        isolated_service.send_message(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5-20250929",
            project_id="proj_abc",
        )

    missing_warnings = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING and "project_id" in rec.getMessage()
    ]
    assert not missing_warnings, (
        f"unexpected project_id warning when project_id was passed: "
        f"{[r.getMessage() for r in missing_warnings]}"
    )
