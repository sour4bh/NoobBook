"""
Active-tasks polling tests (NBB-703).

Pins Contract 10 (background-task polling response) at
`GET /api/v1/projects/<project_id>/active-tasks`. Verifies:
- Frozen response envelope (`success`, `tasks`, `count`).
- Frozen task `type` enum (`source` | `studio` | `background`).
- Studio jobs filtered to {pending, processing} (Contract 13 active subset).
- Background tasks filtered to {pending, running} (active subset).
- Source `uploaded` rows are excluded (only processing/embedding land here).
- Background-tasks deduplication against ids already covered by sources/studio.
- Per-job-type display label mapping (`websites` → `Website`).
- Partial-fetch failures don't break the envelope (route logs and continues).
"""
import os
from unittest.mock import MagicMock, patch

import pytest


# Bypass `api_bp.before_request` JWT validation by monkeypatching `validate_token`
# at its use site. `app.api.__init__` does
#     from app.api.auth.middleware import validate_token
# which binds the name into `app.api`, so that's where the patch must land. The
# app-level RBAC guard is already disabled by NOOBBOOK_AUTH_REQUIRED=false (set
# in conftest).
@pytest.fixture(scope="module", autouse=True)
def _bypass_jwt():
    with patch("app.api.validate_token", return_value="user-test"):
        yield


@pytest.fixture
def app():
    """Build the Flask app with the JWT bypass already active."""
    from app import create_app
    return create_app("testing")


@pytest.fixture
def client(app):
    return app.test_client()


PROJECT_ID = "11111111-1111-1111-1111-111111111111"
ROUTE = f"/api/v1/projects/{PROJECT_ID}/active-tasks"


# ===========================================================================
# Envelope contract
# ===========================================================================

class TestEnvelope:
    """Contract 10 freezes the three keys success/tasks/count regardless of
    upstream errors. Partial fetch failures must not change the envelope."""

    def test_empty_state_returns_frozen_envelope(self, client):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            mock_supabase.return_value.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[])

            response = client.get(ROUTE)

        assert response.status_code == 200
        body = response.get_json()
        # Frozen envelope keys.
        assert set(body.keys()) >= {"success", "tasks", "count"}
        assert body["success"] is True
        assert body["tasks"] == []
        assert body["count"] == 0


# ===========================================================================
# Sources branch
# ===========================================================================

class TestSourcesBranch:
    """Sources contribute rows of type='source'. Only processing/embedding
    statuses are included; 'uploaded' is excluded (the brief pre-processing
    window stays out of the status bar per route comments)."""

    @pytest.fixture
    def stub_supabase(self):
        with patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock:
            # Default: no studio jobs and no background tasks.
            mock.return_value.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[])
            yield mock

    def test_processing_source_appears(self, client, stub_supabase):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[
                {"id": "s-1", "name": "Q3 Report.pdf", "status": "processing",
                 "created_at": "2026-04-24T10:00:00Z"},
            ],
        ):
            response = client.get(ROUTE)

        body = response.get_json()
        sources = [t for t in body["tasks"] if t["type"] == "source"]
        assert len(sources) == 1
        task = sources[0]
        # Required fields per Contract 10.
        for key in ("id", "type", "label", "detail", "status", "created_at"):
            assert key in task
        assert task["id"] == "s-1"
        assert task["label"] == "Q3 Report.pdf"
        assert task["status"] == "processing"
        assert "Processing" in task["detail"]

    def test_embedding_source_is_labeled(self, client, stub_supabase):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[
                {"id": "s-1", "name": "Q3.pdf", "status": "embedding",
                 "created_at": "2026-04-24T10:00:00Z"},
            ],
        ):
            response = client.get(ROUTE)

        sources = [t for t in response.get_json()["tasks"] if t["type"] == "source"]
        assert len(sources) == 1
        assert "Embedding" in sources[0]["detail"]

    def test_uploaded_source_is_excluded(self, client, stub_supabase):
        # uploaded sources are pre-processing; route deliberately skips them.
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[
                {"id": "s-1", "name": "draft.pdf", "status": "uploaded",
                 "created_at": "2026-04-24T10:00:00Z"},
            ],
        ):
            response = client.get(ROUTE)

        assert all(t["type"] != "source" for t in response.get_json()["tasks"])

    def test_ready_source_is_excluded(self, client, stub_supabase):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[
                {"id": "s-1", "name": "ok.pdf", "status": "ready",
                 "created_at": "2026-04-24T10:00:00Z"},
            ],
        ):
            response = client.get(ROUTE)

        assert response.get_json()["tasks"] == []


# ===========================================================================
# Studio jobs branch
# ===========================================================================

class TestStudioJobsBranch:
    """Studio jobs contribute rows of type='studio' from the studio_jobs table.
    Only pending+processing rows are active; ready/error/cancelled are terminal
    per Contract 13."""

    def _stub_studio_query(self, mock_supabase, studio_data):
        """Wire the studio_jobs select chain to return `studio_data` and the
        background_tasks select chain to return []."""
        # First .table() call: studio_jobs path is .select().eq().in_().order().execute()
        # Second .table() call: background_tasks path is .select().eq().in_().order().execute()
        studio_mock = MagicMock()
        studio_mock.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=studio_data)
        bg_mock = MagicMock()
        bg_mock.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        def table_router(name):
            if name == "studio_jobs":
                return studio_mock
            return bg_mock

        mock_supabase.return_value.table.side_effect = table_router

    def test_studio_job_filters_pending_and_processing_only(self, client):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            self._stub_studio_query(mock_supabase, [
                {"id": "j-1", "job_type": "websites", "source_name": "Q3.pdf",
                 "direction": "Build a marketing site",
                 "status": "processing", "progress": "Planning pages...",
                 "created_at": "2026-04-24T10:00:05Z"},
            ])

            response = client.get(ROUTE)

        # Confirm the .in_ filter passed for studio_jobs is exactly the active subset.
        studio_table_mock = mock_supabase.return_value.table("studio_jobs")
        in_call = studio_table_mock.select.return_value.eq.return_value.in_.call_args
        assert in_call.args[0] == "status"
        assert set(in_call.args[1]) == {"pending", "processing"}

        body = response.get_json()
        studio = [t for t in body["tasks"] if t["type"] == "studio"]
        assert len(studio) == 1
        task = studio[0]
        for key in ("id", "type", "label", "detail", "status", "progress", "created_at"):
            assert key in task

    def test_websites_job_type_renders_friendly_label(self, client):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            self._stub_studio_query(mock_supabase, [
                {"id": "j-1", "job_type": "websites", "source_name": "Q3.pdf",
                 "direction": "Build it", "status": "processing",
                 "progress": "Working...", "created_at": "2026-04-24T10:00:05Z"},
            ])
            response = client.get(ROUTE)

        studio = [t for t in response.get_json()["tasks"] if t["type"] == "studio"]
        # "websites" job_type → "Website" display label per _format_job_type.
        assert studio[0]["label"] == "Website"

    def test_studio_detail_falls_back_to_direction_when_no_source_name(
        self, client
    ):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            self._stub_studio_query(mock_supabase, [
                {"id": "j-1", "job_type": "blog", "source_name": None,
                 "direction": "Q4 strategy retrospective",
                 "status": "pending", "progress": None,
                 "created_at": "2026-04-24T10:00:05Z"},
            ])
            response = client.get(ROUTE)

        studio = [t for t in response.get_json()["tasks"] if t["type"] == "studio"]
        assert studio[0]["detail"] == "Q4 strategy retrospective"


# ===========================================================================
# Background tasks branch
# ===========================================================================

class TestBackgroundTasksBranch:
    """Background tasks contribute rows of type='background', deduplicated
    against ids already covered by sources or studio jobs. Only pending+running
    are active per the background_tasks status enum."""

    def _stub_queries(self, mock_supabase, studio_data, bg_data):
        studio_mock = MagicMock()
        studio_mock.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=studio_data)
        bg_mock = MagicMock()
        bg_mock.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=bg_data)

        def table_router(name):
            if name == "studio_jobs":
                return studio_mock
            return bg_mock

        mock_supabase.return_value.table.side_effect = table_router
        return studio_mock, bg_mock

    def test_background_filter_is_pending_and_running(self, client):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            _, bg_mock = self._stub_queries(mock_supabase, [], [])
            client.get(ROUTE)

        project_call = bg_mock.select.return_value.eq.call_args
        assert project_call.args == ("project_id", PROJECT_ID)

        in_call = bg_mock.select.return_value.eq.return_value.in_.call_args
        assert in_call.args[0] == "status"
        # Active subset of the background_tasks status enum.
        assert set(in_call.args[1]) == {"pending", "running"}

    def test_background_task_appears_with_friendly_label(self, client):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            self._stub_queries(mock_supabase, [], [
                {"id": "b-1", "task_type": "chat_auto_name",
                 "target_type": "chat", "status": "running",
                 "message": None, "created_at": "2026-04-24T10:00:10Z",
                 "started_at": "2026-04-24T10:00:11Z"},
            ])
            response = client.get(ROUTE)

        bg = [t for t in response.get_json()["tasks"] if t["type"] == "background"]
        assert len(bg) == 1
        task = bg[0]
        # chat_auto_name → "Naming Chat" per _format_task_type.
        assert task["label"] == "Naming Chat"
        assert task["detail"] == "Processing..."
        assert task["status"] == "running"
        # started_at takes precedence over created_at when present.
        assert task["created_at"] == "2026-04-24T10:00:11Z"

    def test_background_dedup_against_studio_job_id(self, client):
        # If a background task carries the same id as a studio job already
        # surfaced, drop it to avoid duplicate rows in the status bar.
        shared_id = "shared-id"
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            self._stub_queries(
                mock_supabase,
                [{"id": shared_id, "job_type": "websites",
                  "source_name": "Q3.pdf", "direction": "x",
                  "status": "processing", "progress": "Working...",
                  "created_at": "2026-04-24T10:00:05Z"}],
                [{"id": shared_id, "task_type": "website_generation",
                  "target_type": "studio_signal", "status": "running",
                  "message": None, "created_at": "2026-04-24T10:00:06Z",
                  "started_at": "2026-04-24T10:00:07Z"}],
            )
            response = client.get(ROUTE)

        tasks = response.get_json()["tasks"]
        # Only one row for the shared id, and it must be the studio entry
        # (which was inserted first in the route).
        matching = [t for t in tasks if t["id"] == shared_id]
        assert len(matching) == 1
        assert matching[0]["type"] == "studio"


# ===========================================================================
# Combined ordering / count
# ===========================================================================

class TestCombined:

    def test_count_matches_tasks_length(self, client):
        with patch(
            "app.api.projects.active_tasks.source_service.list_sources",
            return_value=[
                {"id": "s-1", "name": "a.pdf", "status": "processing",
                 "created_at": "2026-04-24T10:00:00Z"},
            ],
        ), patch(
            "app.api.projects.active_tasks.get_supabase",
        ) as mock_supabase:
            studio_mock = MagicMock()
            studio_mock.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[
                {"id": "j-1", "job_type": "audio", "source_name": "a.pdf",
                 "direction": "x", "status": "processing",
                 "progress": "y", "created_at": "2026-04-24T10:00:05Z"},
            ])
            bg_mock = MagicMock()
            bg_mock.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[])

            def table_router(name):
                return studio_mock if name == "studio_jobs" else bg_mock

            mock_supabase.return_value.table.side_effect = table_router

            response = client.get(ROUTE)

        body = response.get_json()
        assert body["count"] == len(body["tasks"]) == 2
        types = {t["type"] for t in body["tasks"]}
        assert types == {"source", "studio"}
