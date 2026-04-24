"""
Focused cost-tracking regression: ``claude_service.send_message`` must make
missing ``project_id`` observable so the pre-migration taste-audit fix in
NBB-109 cannot silently regress.

The full cost math has its own suite in ``test_cost_tracking.py``. This file
only proves the cost-tracking entry point (``send_message``):

1. logs a warning when ``project_id`` is falsy so broken call sites are
   greppable in production logs, and
2. still skips the ``add_cost_usage`` call — the warning is a detector, not a
   behavior change.

Both the network call and the ``anthropic.Anthropic`` client are stubbed out
so the test does not depend on ANTHROPIC_API_KEY.
"""
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sys

from app.services.integrations.claude.claude_service import ClaudeService

# The package ``__init__`` re-exports the singleton under the name
# ``claude_service``, which shadows the module binding on the parent package.
# Pull the underlying module out of ``sys.modules`` to reach its logger.
_CLAUDE_MODULE = sys.modules["app.services.integrations.claude.claude_service"]
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
def isolated_service():
    """Fresh ClaudeService with API + spending-limit side effects stubbed."""
    service = ClaudeService()

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: _fake_anthropic_response())
    )

    with patch.object(service, "_get_client", return_value=fake_client), patch(
        "app.services.integrations.claude.claude_service.check_user_spending_limit",
        return_value=None,
    ):
        yield service


def test_send_message_without_project_id_logs_warning(isolated_service, caplog):
    """Missing project_id must produce a WARNING record mentioning project_id."""
    with caplog.at_level(logging.WARNING, logger=_CLAUDE_LOGGER_NAME), patch(
        "app.services.integrations.claude.claude_service.add_cost_usage"
    ) as mock_add_cost:
        isolated_service.send_message(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5-20250929",
        )

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any("project_id" in rec.getMessage() for rec in warnings), (
        f"expected a warning mentioning project_id, got: {[r.getMessage() for r in warnings]}"
    )
    # Cost tracking must stay skipped so we do not write bogus rows for unknown projects.
    mock_add_cost.assert_not_called()


def test_send_message_with_project_id_records_cost(isolated_service, caplog):
    """When project_id is passed, no warning fires and costs are recorded."""
    with caplog.at_level(logging.WARNING, logger=_CLAUDE_LOGGER_NAME), patch(
        "app.services.integrations.claude.claude_service.add_cost_usage"
    ) as mock_add_cost:
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
    mock_add_cost.assert_called_once()
    call_kwargs = mock_add_cost.call_args.kwargs
    assert call_kwargs.get("project_id") == "proj_abc"
