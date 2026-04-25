"""
Background task linkage tests (NBB-703).

Pins `app.background.tasks.task_service.submit_task` and the surrounding
lifecycle wiring (status transitions, error capture, cleanup of stale state).
This is the substrate every studio item's `run.py` builds on.

Status enum (background_tasks): pending | running | completed | failed | cancelled.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.background import tasks as tasks_module
from app.background.tasks import task_service


# Frozen background_tasks status enum. Active-tasks polling (Contract 10)
# filters this table on {pending, running}; the rest are terminal.
BG_STATUS_VALUES = {"pending", "running", "completed", "failed", "cancelled"}


@pytest.fixture
def supabase_client():
    """Mock the Supabase client that `_get_supabase` returns inside tasks.py."""
    client = MagicMock()
    with patch.object(tasks_module, "_get_supabase", return_value=client):
        yield client


@pytest.fixture
def synchronous_executor(monkeypatch):
    """Replace `_executor.submit` with a synchronous runner.

    `task_service.submit_task` returns immediately when running async; for
    behavior tests we need the wrapper's status transitions to actually fire.
    Capture the wrapper, run it inline, and return a fake Future.
    """
    captured = {}

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        # Execute now so status transitions land in the mock supabase calls.
        try:
            captured["result"] = func()
        except Exception as e:
            captured["exception"] = e
        future = MagicMock()
        future.cancel.return_value = True
        return future

    monkeypatch.setattr(task_service._executor, "submit", fake_submit)
    return captured


@pytest.fixture(autouse=True)
def reset_singleton_state(monkeypatch):
    """Snapshot/restore the singleton's mutable attributes around each test.

    `task_service` is a module-level singleton; `_cancelled_tasks` and
    `_futures` carry between tests if not reset. Pattern mirrors the MCP
    tool_capability_policy snapshot recorded in NBB-701's commit 0f0181a.
    """
    monkeypatch.setattr(task_service, "_cancelled_tasks", set())
    monkeypatch.setattr(task_service, "_futures", {})


# ===========================================================================
# Status enum invariant
# ===========================================================================

class TestBackgroundStatusEnum:

    def test_enum_is_frozen(self):
        # Hardcoded set in the test file; if tasks.py adds a status, the
        # downstream poll route filters in active_tasks.py also need updating.
        assert BG_STATUS_VALUES == {
            "pending", "running", "completed", "failed", "cancelled"
        }


# ===========================================================================
# Submit + status transitions
# ===========================================================================

class TestSubmitTask:
    """submit_task creates a pending row, runs the wrapper, and writes
    running → completed (success) or running → failed (exception)."""

    def test_submit_records_pending_row_with_metadata(
        self, supabase_client, synchronous_executor
    ):
        callable_func = MagicMock(return_value="ok")

        task_id = task_service.submit_task(
            task_type="website_generation",
            target_id="job-1",
            callable_func=callable_func,
            target_type="studio_signal",
        )

        # First .insert(...) is the pending-row write.
        insert_calls = supabase_client.table.return_value.insert.call_args_list
        assert insert_calls, "submit_task must persist a pending row"
        pending_row = insert_calls[0].args[0]
        assert pending_row["id"] == task_id
        assert pending_row["task_type"] == "website_generation"
        assert pending_row["target_id"] == "job-1"
        assert pending_row["target_type"] == "studio_signal"
        assert pending_row["status"] == "pending"
        assert pending_row["status"] in BG_STATUS_VALUES
        assert pending_row["progress"] == 0
        assert pending_row["error_message"] is None

    def test_success_path_transitions_running_then_completed(
        self, supabase_client, synchronous_executor
    ):
        callable_func = MagicMock(return_value="result-payload")

        task_service.submit_task(
            task_type="website_generation",
            target_id="job-1",
            callable_func=callable_func,
        )

        # The wrapper updates status: running, then completed.
        update_payloads = [
            call.args[0]
            for call in supabase_client.table.return_value.update.call_args_list
        ]
        statuses = [p.get("status") for p in update_payloads if "status" in p]
        assert "running" in statuses
        assert "completed" in statuses
        assert statuses.index("running") < statuses.index("completed")
        # Completed payload sets progress to 100 and a completed_at stamp.
        completed = next(p for p in update_payloads if p.get("status") == "completed")
        assert completed["progress"] == 100
        assert completed.get("completed_at")
        # Underlying callable runs exactly once with the studio signal context.
        callable_func.assert_called_once()

    def test_failure_path_transitions_running_then_failed_with_error(
        self, supabase_client, synchronous_executor
    ):
        boom = RuntimeError("agent crashed")
        callable_func = MagicMock(side_effect=boom)

        task_service.submit_task(
            task_type="website_generation",
            target_id="job-2",
            callable_func=callable_func,
        )

        update_payloads = [
            call.args[0]
            for call in supabase_client.table.return_value.update.call_args_list
        ]
        statuses = [p.get("status") for p in update_payloads if "status" in p]
        assert "failed" in statuses
        failed = next(p for p in update_payloads if p.get("status") == "failed")
        assert failed["error_message"] == "agent crashed"
        assert failed.get("completed_at")

    def test_callable_args_and_kwargs_are_forwarded(
        self, supabase_client, synchronous_executor
    ):
        callable_func = MagicMock(return_value=None)

        task_service.submit_task(
            "audio_generation",
            "job-3",
            callable_func,
            "positional-1",
            keyword_arg="kw-value",
        )

        callable_func.assert_called_once_with("positional-1", keyword_arg="kw-value")

    def test_future_tracking_clears_after_wrapper_finally(
        self, supabase_client, monkeypatch
    ):
        """Production order: executor.submit registers the future first, then
        the worker thread runs the wrapper. The wrapper's finally-block then
        discards the registration. Simulate that order by deferring the
        wrapper invocation until AFTER submit() returns."""
        captured = {}

        def deferred_submit(func, *args, **kwargs):
            captured["func"] = func
            future = MagicMock()
            future.cancel.return_value = True
            return future

        monkeypatch.setattr(task_service._executor, "submit", deferred_submit)

        callable_func = MagicMock(return_value="done")
        task_id = task_service.submit_task(
            task_type="website_generation",
            target_id="job-4",
            callable_func=callable_func,
        )

        # After submit returns the future is registered.
        assert task_id in task_service._futures

        # Now run the wrapper as the worker thread would.
        captured["func"]()

        # Wrapper finally-block discards both tracking entries.
        assert task_id not in task_service._futures
        assert task_id not in task_service._cancelled_tasks


# ===========================================================================
# Read helpers
# ===========================================================================

class TestGetTask:

    def test_get_task_aliases_task_type_to_type_for_callers(self, supabase_client):
        select_chain = supabase_client.table.return_value.select.return_value.eq.return_value
        select_chain.execute.return_value = MagicMock(data=[{
            "id": "t-1",
            "task_type": "website_generation",
            "target_id": "job-1",
            "status": "running",
        }])

        task = task_service.get_task("t-1")

        # Backward-compat alias used by callers reading legacy attribute.
        assert task["type"] == "website_generation"
        assert task["task_type"] == "website_generation"
        assert task["status"] == "running"

    def test_get_task_returns_none_when_missing(self, supabase_client):
        select_chain = supabase_client.table.return_value.select.return_value.eq.return_value
        select_chain.execute.return_value = MagicMock(data=[])

        assert task_service.get_task("missing") is None

    def test_get_tasks_for_target_returns_list_with_type_alias(self, supabase_client):
        select_chain = supabase_client.table.return_value.select.return_value.eq.return_value
        select_chain.execute.return_value = MagicMock(data=[
            {"id": "t-1", "task_type": "website_generation", "target_id": "job-1",
             "status": "running"},
            {"id": "t-2", "task_type": "website_generation", "target_id": "job-1",
             "status": "completed"},
        ])

        tasks = task_service.get_tasks_for_target("job-1")

        assert len(tasks) == 2
        assert all(t["type"] == "website_generation" for t in tasks)


# ===========================================================================
# Cleanup of stale tasks
# ===========================================================================

class TestStaleTaskCleanup:
    """Server restart leaves rows stuck in pending/running. _cleanup_stale_tasks
    flips them to failed at TaskService.__init__. That hook must touch the
    pending+running set, not the terminal statuses, or you double-fail
    completed work."""

    def test_cleanup_targets_pending_and_running_only(self, supabase_client):
        update_chain = supabase_client.table.return_value.update.return_value
        update_chain.in_.return_value.execute.return_value = MagicMock(data=[])

        task_service._cleanup_stale_tasks()

        update_chain.in_.assert_called_with(
            "status", ["pending", "running"]
        )
        # The status the cleanup flips to is "failed", not "cancelled".
        update_args, _ = supabase_client.table.return_value.update.call_args
        assert update_args[0]["status"] == "failed"
        assert update_args[0]["error_message"] == "Server restarted while task was running"
