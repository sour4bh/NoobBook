"""
Cancellation lifecycle tests (NBB-703).

Pins the cooperative-cancellation contract from `app.background.tasks`:
- `cancel_task(task_id)` returns False for unknown ids and for terminal-state
  tasks (completed/failed/cancelled).
- `cancel_task(task_id)` returns True and writes status=cancelled for pending
  or running tasks, and adds the id to the in-memory `_cancelled_tasks` set.
- `is_cancelled(task_id)` reflects the in-memory set.
- `is_target_cancelled(target_id)` aggregates across all tasks for a target.
- `cancel_tasks_for_target(target_id)` cancels every active task for a target.

The studio item run.py contract relies on these so the agentic loop can break
out cooperatively when the user clicks Cancel in the UI.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.background import tasks as tasks_module
from app.background.tasks import task_service


@pytest.fixture
def supabase_client():
    client = MagicMock()
    with patch.object(tasks_module, "_get_supabase", return_value=client):
        yield client


@pytest.fixture(autouse=True)
def reset_singleton_state(monkeypatch):
    """Snapshot/restore mutable singleton state per test."""
    monkeypatch.setattr(task_service, "_cancelled_tasks", set())
    monkeypatch.setattr(task_service, "_futures", {})


def _stub_get_task(supabase_client, task_record):
    """Wire `.select("*").eq("id", X).execute()` to return one row (or none)."""
    select_chain = supabase_client.table.return_value.select.return_value.eq.return_value
    select_chain.execute.return_value = MagicMock(
        data=[task_record] if task_record else []
    )


def _stub_get_tasks_for_target(supabase_client, rows):
    """Wire `.select("*").eq("target_id", X).execute()` to return rows."""
    select_chain = supabase_client.table.return_value.select.return_value.eq.return_value
    select_chain.execute.return_value = MagicMock(data=rows)


# ===========================================================================
# cancel_task return-value contract
# ===========================================================================

class TestCancelTaskReturnValue:

    def test_unknown_task_returns_false(self, supabase_client):
        _stub_get_task(supabase_client, None)

        assert task_service.cancel_task("missing") is False

    @pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled"])
    def test_terminal_state_task_returns_false_without_marking(
        self, supabase_client, terminal_status
    ):
        _stub_get_task(supabase_client, {
            "id": "t-1", "task_type": "website_generation",
            "status": terminal_status,
        })

        assert task_service.cancel_task("t-1") is False
        # Terminal tasks must not be added to the cancelled set; doing so would
        # poison `is_cancelled` for tasks that already finished.
        assert "t-1" not in task_service._cancelled_tasks

    @pytest.mark.parametrize("active_status", ["pending", "running"])
    def test_active_task_returns_true_and_writes_cancelled_status(
        self, supabase_client, active_status
    ):
        _stub_get_task(supabase_client, {
            "id": "t-1", "task_type": "website_generation",
            "status": active_status,
        })

        # Track the future so cancel_task tries to cancel it.
        future = MagicMock()
        task_service._futures["t-1"] = future

        assert task_service.cancel_task("t-1") is True
        assert "t-1" in task_service._cancelled_tasks
        future.cancel.assert_called_once()

        # cancelled status is written to Supabase along with completed_at.
        update_payloads = [
            call.args[0]
            for call in supabase_client.table.return_value.update.call_args_list
        ]
        statuses = [p.get("status") for p in update_payloads]
        assert "cancelled" in statuses
        cancelled_payload = next(p for p in update_payloads if p.get("status") == "cancelled")
        assert cancelled_payload["error_message"] == "Cancelled by user"
        assert cancelled_payload.get("completed_at")


# ===========================================================================
# is_cancelled / is_target_cancelled
# ===========================================================================

class TestIsCancelled:

    def test_returns_true_when_id_in_cancelled_set(self):
        task_service._cancelled_tasks.add("t-1")

        assert task_service.is_cancelled("t-1") is True

    def test_returns_false_when_id_absent(self):
        assert task_service.is_cancelled("never-cancelled") is False


class TestIsTargetCancelled:
    """Long-running studio loops don't always know their own task_id; they
    poll by source_id/job_id and need a transitive check."""

    def test_returns_true_when_any_target_task_in_memory_cancelled_set(
        self, supabase_client
    ):
        _stub_get_tasks_for_target(supabase_client, [
            {"id": "t-1", "task_type": "website_generation", "status": "running"},
            {"id": "t-2", "task_type": "website_generation", "status": "running"},
        ])
        task_service._cancelled_tasks.add("t-2")

        assert task_service.is_target_cancelled("job-1") is True

    def test_returns_true_when_any_target_task_status_is_cancelled(
        self, supabase_client
    ):
        # In-memory set may be empty after a server restart, but the persisted
        # row still says cancelled. Honor that.
        _stub_get_tasks_for_target(supabase_client, [
            {"id": "t-1", "task_type": "website_generation", "status": "cancelled"},
        ])

        assert task_service.is_target_cancelled("job-1") is True

    def test_returns_false_when_all_tasks_are_active_or_complete(
        self, supabase_client
    ):
        _stub_get_tasks_for_target(supabase_client, [
            {"id": "t-1", "task_type": "website_generation", "status": "running"},
            {"id": "t-2", "task_type": "website_generation", "status": "completed"},
        ])

        assert task_service.is_target_cancelled("job-1") is False


# ===========================================================================
# cancel_tasks_for_target — bulk cancellation
# ===========================================================================

class TestCancelTasksForTarget:
    """When a user deletes a source mid-processing, every task for that source
    is cancelled. Only pending/running rows count."""

    def test_cancels_only_pending_and_running_tasks(
        self, supabase_client, monkeypatch
    ):
        # Stub get_tasks_for_target with mixed statuses.
        all_rows = [
            {"id": "t-1", "task_type": "website_generation", "status": "running"},
            {"id": "t-2", "task_type": "website_generation", "status": "pending"},
            {"id": "t-3", "task_type": "website_generation", "status": "completed"},
            {"id": "t-4", "task_type": "website_generation", "status": "failed"},
        ]
        # Bypass real cancel_task wiring; assert which ids get cancelled.
        cancelled = []

        def fake_cancel_task(task_id):
            cancelled.append(task_id)
            return True

        monkeypatch.setattr(task_service, "get_tasks_for_target", lambda target_id: all_rows)
        monkeypatch.setattr(task_service, "cancel_task", fake_cancel_task)

        count = task_service.cancel_tasks_for_target("job-1")

        assert count == 2
        assert set(cancelled) == {"t-1", "t-2"}

    def test_returns_zero_when_no_active_tasks(
        self, supabase_client, monkeypatch
    ):
        all_rows = [
            {"id": "t-1", "task_type": "website_generation", "status": "completed"},
        ]
        monkeypatch.setattr(task_service, "get_tasks_for_target", lambda target_id: all_rows)
        # cancel_task should never be called for terminal-state rows.
        monkeypatch.setattr(
            task_service, "cancel_task",
            MagicMock(side_effect=AssertionError("must not be called for terminal rows")),
        )

        assert task_service.cancel_tasks_for_target("job-1") == 0
