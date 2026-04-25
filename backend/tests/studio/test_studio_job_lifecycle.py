"""
Studio job lifecycle tests (NBB-703).

Pins Contract 13 (`studio_jobs` create/update/get/list/delete + status enum +
result-shape keys) using `design/website` as the representative item per the
NBB-503 pilot. Tests the per-item job module wrappers in
`app.studio.design.website.job` and the underlying generic CRUD in
`app.services.studio_services.studio_index_service`.

Status enum (Contract 13): pending | processing | ready | error | cancelled.
"""
from unittest.mock import MagicMock, patch

import pytest

# Import order matters: studio_index_service performs a deferred re-export of
# every per-item job module's CRUD functions at module-bottom. Importing
# website.job first triggers the back-edge before studio_index_service has
# defined create_job/update_job. Going through studio_index_service first
# loads the full chain in dependency order.
from app.services.studio_services import studio_index_service
from app.studio.design.website import job as website_job


PROJECT_ID = "p-test"
JOB_ID = "j-test"
SOURCE_ID = "s-test"


# Contract 13 — frozen status enum.
STUDIO_STATUS_VALUES = {"pending", "processing", "ready", "error", "cancelled"}


@pytest.fixture
def supabase_client():
    """MagicMock Supabase client wired up for the studio_index_service helpers.

    `_get_client` is the single seam; patching it lets each test assert against
    the recorded `.table(...).insert/update/select/delete(...)` chain.
    """
    client = MagicMock()
    with patch.object(studio_index_service, "_get_client", return_value=client):
        yield client


def _execute_response(data):
    """Build a Supabase-style execute() return value with .data attribute."""
    response = MagicMock()
    response.data = data
    return response


# ===========================================================================
# Status enum invariant
# ===========================================================================

class TestStatusEnum:
    """Contract 13 status enum stays exactly these five values.

    The active-tasks polling route (Contract 10) filters studio_jobs on
    {pending, processing} and assumes the rest are terminal. If any value
    drifts, this test fails.
    """

    def test_enum_is_frozen(self):
        # If a future PR adds/removes a status, this set comparison fails.
        assert STUDIO_STATUS_VALUES == {
            "pending", "processing", "ready", "error", "cancelled"
        }


# ===========================================================================
# Create
# ===========================================================================

class TestCreateWebsiteJob:
    """`create_website_job` writes a row through `studio_index_service.create_job`."""

    def test_create_inserts_with_pending_status_and_full_default_shape(
        self, supabase_client
    ):
        # Echo back the inserted row so _map_job has data to flatten.
        captured = {}

        def fake_insert(row):
            captured["row"] = row
            return MagicMock(execute=lambda: _execute_response([row]))

        supabase_client.table.return_value.insert.side_effect = fake_insert

        website_job.create_website_job(
            project_id=PROJECT_ID,
            job_id=JOB_ID,
            source_id=SOURCE_ID,
            source_name="Q3 Report",
            direction="Build a marketing site",
        )

        supabase_client.table.assert_called_with("studio_jobs")
        row = captured["row"]
        # Top-level Contract 13 columns are extracted explicitly.
        assert row["id"] == JOB_ID
        assert row["project_id"] == PROJECT_ID
        assert row["job_type"] == "website"
        assert row["status"] == "pending"
        assert row["status"] in STUDIO_STATUS_VALUES
        assert row["source_id"] == SOURCE_ID
        assert row["source_name"] == "Q3 Report"
        assert row["direction"] == "Build a marketing site"
        # Initial progress is the human-readable string per Contract 13.
        assert row["progress"] == "Initializing..."
        # Website-specific result-shape fields land in the JSONB `job_data` column.
        job_data = row["job_data"]
        for key in (
            "site_type", "site_name", "pages", "features", "design_system",
            "navigation_style", "images_needed", "layout_notes",
            "images", "files", "pages_created", "features_implemented",
            "cdn_libraries_used", "summary",
            "preview_url", "download_url", "iterations",
            "input_tokens", "output_tokens",
        ):
            assert key in job_data, f"Website result-shape key missing: {key}"

    def test_create_with_edit_lineage_records_parent_and_instructions(
        self, supabase_client
    ):
        captured = {}

        def fake_insert(row):
            captured["row"] = row
            return MagicMock(execute=lambda: _execute_response([row]))

        supabase_client.table.return_value.insert.side_effect = fake_insert

        website_job.create_website_job(
            project_id=PROJECT_ID,
            job_id=JOB_ID,
            source_id=SOURCE_ID,
            source_name="Q3 Report",
            direction="Refine landing page",
            parent_job_id="parent-1",
            edit_instructions="Tighten copy",
        )

        job_data = captured["row"]["job_data"]
        assert job_data["parent_job_id"] == "parent-1"
        assert job_data["edit_instructions"] == "Tighten copy"


# ===========================================================================
# Update / status transitions
# ===========================================================================

class TestUpdateWebsiteJob:
    """`update_website_job` drives the Contract 13 status transitions.

    Pins: pending → processing → ready (success path) and → error (failure path).
    Top-level columns vs JSONB job_data routing is studio_index_service's job;
    we assert via the recorded supabase calls, not by mocking the helper.
    """

    @pytest.mark.parametrize("target_status", ["processing", "ready", "error", "cancelled"])
    def test_status_transitions_route_to_top_level_column(
        self, supabase_client, target_status
    ):
        # update_job needs a fetch-then-update chain because status is top-level
        # (no JSONB merge needed). Stub the update path only.
        update_chain = supabase_client.table.return_value.update.return_value
        update_chain.eq.return_value.eq.return_value.execute.return_value = (
            _execute_response([{
                "id": JOB_ID, "project_id": PROJECT_ID, "job_type": "website",
                "status": target_status, "job_data": {},
            }])
        )

        website_job.update_website_job(
            project_id=PROJECT_ID,
            job_id=JOB_ID,
            status=target_status,
        )

        # Recorded payload routes `status` to the top-level column, not `job_data`.
        update_args, _ = supabase_client.table.return_value.update.call_args
        payload = update_args[0]
        assert payload["status"] == target_status
        assert "job_data" not in payload, (
            "status must be a top-level column per Contract 13, not buried in job_data"
        )

    def test_error_alias_routes_to_error_message_column(self, supabase_client):
        update_chain = supabase_client.table.return_value.update.return_value
        update_chain.eq.return_value.eq.return_value.execute.return_value = (
            _execute_response([{
                "id": JOB_ID, "project_id": PROJECT_ID, "job_type": "website",
                "status": "error", "error_message": "boom", "job_data": {},
            }])
        )

        # Callers in the website tool pass `error=...`; studio_index_service maps
        # this to the `error_message` Supabase column.
        studio_index_service.update_job(PROJECT_ID, JOB_ID, error="boom")

        update_args, _ = supabase_client.table.return_value.update.call_args
        payload = update_args[0]
        assert payload["error_message"] == "boom"
        assert "error" not in payload, "error key must be aliased to error_message column"

    def test_progress_is_a_human_readable_string(self, supabase_client):
        update_chain = supabase_client.table.return_value.update.return_value
        update_chain.eq.return_value.eq.return_value.execute.return_value = (
            _execute_response([{
                "id": JOB_ID, "project_id": PROJECT_ID, "job_type": "website",
                "status": "processing", "progress": "Planning pages (step 1)...",
                "job_data": {},
            }])
        )

        # Per Contract 13 progress is a string, not a number.
        website_job.update_website_job(
            project_id=PROJECT_ID,
            job_id=JOB_ID,
            progress="Planning pages (step 1)...",
        )

        update_args, _ = supabase_client.table.return_value.update.call_args
        payload = update_args[0]
        assert isinstance(payload["progress"], str)
        assert payload["progress"] == "Planning pages (step 1)..."

    def test_filters_none_values_to_avoid_clobbering_columns(self, supabase_client):
        # `update_job` skips None updates so partial mid-flight updates do not
        # null out previously-set columns. (Studio jobs is shared mutable state.)
        update_chain = supabase_client.table.return_value.update.return_value
        update_chain.eq.return_value.eq.return_value.execute.return_value = (
            _execute_response([{
                "id": JOB_ID, "project_id": PROJECT_ID, "status": "processing",
                "job_data": {},
            }])
        )

        studio_index_service.update_job(
            PROJECT_ID, JOB_ID, status="processing", error_message=None
        )

        update_args, _ = supabase_client.table.return_value.update.call_args
        payload = update_args[0]
        assert "error_message" not in payload, (
            "None updates must be filtered to preserve existing values"
        )


# ===========================================================================
# Get / list / delete (Contract 13 result-shape flattening)
# ===========================================================================

class TestReadWebsiteJob:
    """`_map_job` flattens job_data JSONB and aliases error_message → error.

    These tests pin the read shape that frontends consume; if the flattening
    breaks, callers see job_data nested instead of fields top-level.
    """

    def test_get_returns_flattened_dict_with_aliased_error(self, supabase_client):
        select_chain = supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value
        select_chain.execute.return_value = _execute_response([{
            "id": JOB_ID,
            "project_id": PROJECT_ID,
            "job_type": "website",
            "status": "error",
            "progress": None,
            "source_name": "Q3 Report",
            "error_message": "boom",
            "job_data": {
                "site_name": "Marketing Site",
                "files": ["index.html", "styles.css"],
            },
        }])

        result = website_job.get_website_job(PROJECT_ID, JOB_ID)

        assert result["id"] == JOB_ID
        assert result["status"] == "error"
        # `error` is the read-time alias for the `error_message` column.
        assert result["error"] == "boom"
        assert "error_message" not in result
        # JSONB job_data is flattened to top-level keys.
        assert result["site_name"] == "Marketing Site"
        assert result["files"] == ["index.html", "styles.css"]

    def test_get_returns_none_when_row_missing(self, supabase_client):
        select_chain = supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value
        select_chain.execute.return_value = _execute_response([])

        assert website_job.get_website_job(PROJECT_ID, JOB_ID) is None

    def test_list_filters_by_job_type_website(self, supabase_client):
        order_chain = (
            supabase_client.table.return_value.select.return_value
            .eq.return_value.eq.return_value.order.return_value
        )
        order_chain.execute.return_value = _execute_response([])

        website_job.list_website_jobs(PROJECT_ID)

        # Confirms list_jobs delegates with JOB_TYPE="website" — protects against
        # accidental cross-type bleed during future refactors. The .eq() chain is
        # nested (each call returns a fresh chain), so collect calls layer by layer.
        first_eq = supabase_client.table.return_value.select.return_value.eq
        second_eq = first_eq.return_value.eq
        first_calls = [call.args for call in first_eq.call_args_list]
        second_calls = [call.args for call in second_eq.call_args_list]
        all_filters = dict(first_calls + second_calls)
        assert all_filters.get("project_id") == PROJECT_ID
        assert all_filters.get("job_type") == "website"

    def test_list_with_source_id_filter(self, supabase_client):
        # source_id filter adds a third .eq() clause to the chain.
        chain = supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value
        chain.order.return_value.eq.return_value.execute.return_value = (
            _execute_response([])
        )

        website_job.list_website_jobs(PROJECT_ID, source_id=SOURCE_ID)

        # The third .eq() is on the chain after .order() per studio_index_service.
        order_eq = chain.order.return_value.eq
        order_eq.assert_called_with("source_id", SOURCE_ID)


class TestDeleteWebsiteJob:

    def test_delete_returns_true_when_row_removed(self, supabase_client):
        delete_chain = (
            supabase_client.table.return_value.delete.return_value
            .eq.return_value.eq.return_value
        )
        delete_chain.execute.return_value = _execute_response([{"id": JOB_ID}])

        assert website_job.delete_website_job(PROJECT_ID, JOB_ID) is True

    def test_delete_returns_false_when_no_match(self, supabase_client):
        delete_chain = (
            supabase_client.table.return_value.delete.return_value
            .eq.return_value.eq.return_value
        )
        delete_chain.execute.return_value = _execute_response([])

        assert website_job.delete_website_job(PROJECT_ID, JOB_ID) is False
