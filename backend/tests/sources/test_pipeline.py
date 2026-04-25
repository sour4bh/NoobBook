"""
Source pipeline + catalog smoke tests (NBB-702).

Pipeline contracts pinned here:

1. ``SourcePipeline.PROCESSOR_MAP`` is the single dispatcher for source
   ingestion. Every extension that ``file_contract.ALLOWED_EXTENSIONS``
   accepts as an upload must route to a processor — otherwise the user
   uploads a file the catalog accepted but the pipeline silently parks at
   "uploaded".
2. ``process_source`` fails fast with a structured error when:
   - the source row does not exist in the index,
   - the source row has no ``stored_filename`` (upload incomplete).
3. ``cancel_processing`` only fires for in-flight statuses
   (``uploaded`` / ``processing`` / ``embedding``); it is a no-op for
   terminal states (``ready`` / ``error``).
4. ``retry_processing`` refuses to retry an already-``ready`` source so we
   do not re-download + re-embed already-finished work.

These contracts come from ``backend/app/sources/pipeline.py``; protecting
them keeps the post-NBB-402 ingestion surface from regressing as the
service layer below it continues to migrate.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.sources.catalog import SourceCatalog
from app.sources.file_contract import (
    ALLOWED_EXTENSIONS,
    MAX_IMAGE_SIZE,
    get_file_info,
    get_extensions_by_category,
    is_allowed_file,
    validate_file_size,
)
from app.sources.pipeline import SourcePipeline

from tests.sources.conftest import PROJECT_ID, SOURCE_ID


# ---------------------------------------------------------------------------
# file_contract — accepted kinds and validation
# ---------------------------------------------------------------------------


class TestFileContract:

    def test_pdf_is_allowed_with_document_category(self):
        ext, category, mime = get_file_info("report.pdf")
        assert ext == ".pdf"
        assert category == "document"
        assert mime == "application/pdf"

    def test_csv_is_data_category(self):
        # CSV is its own category (not "document") because CSV sources route
        # to the analysis pipeline rather than the text-extraction pipeline.
        _ext, category, _mime = get_file_info("orders.csv")
        assert category == "data"

    def test_link_extension_is_link_category(self):
        # `.link` is the synthetic extension URL/YouTube uploads use; the
        # frontend distinguishes "link" sources for icon selection.
        _ext, category, mime = get_file_info("youtube.link")
        assert category == "link"
        assert mime == "application/json"

    def test_unknown_extension_is_rejected(self):
        assert is_allowed_file("malware.exe") is False
        ext, category, mime = get_file_info("malware.exe")
        assert ext == ".exe"
        assert category == "unknown"
        assert mime == "application/octet-stream"

    def test_extensions_by_category_groups_known_kinds(self):
        groups = get_extensions_by_category()
        # The five categories the upload UI surfaces.
        assert {"document", "audio", "image", "data", "link"} <= set(groups)
        assert ".pdf" in groups["document"]
        assert ".mp3" in groups["audio"]
        assert ".png" in groups["image"]
        assert ".csv" in groups["data"]

    def test_validate_file_size_blocks_oversized_image(self):
        msg = validate_file_size("photo.jpg", MAX_IMAGE_SIZE + 1)
        assert msg is not None
        assert "Image" in msg

    def test_validate_file_size_passes_within_limit(self):
        assert validate_file_size("photo.jpg", MAX_IMAGE_SIZE) is None

    def test_validate_file_size_does_not_limit_documents(self):
        # No document size cap by design — large PDFs are accepted; the
        # processing pipeline (not the contract) handles cost protection.
        assert validate_file_size("big.pdf", MAX_IMAGE_SIZE * 100) is None


# ---------------------------------------------------------------------------
# SourcePipeline.PROCESSOR_MAP coverage
# ---------------------------------------------------------------------------


class TestProcessorMapCoverage:

    def test_every_uploadable_extension_has_a_processor(self):
        # If the upload contract accepts an extension, the pipeline must
        # route it. Otherwise the catalog would silently drop the source at
        # the dispatcher.
        missing = [
            ext
            for ext in ALLOWED_EXTENSIONS
            if ext not in SourcePipeline.PROCESSOR_MAP
        ]
        assert missing == [], (
            f"ALLOWED_EXTENSIONS missing from PROCESSOR_MAP: {missing}"
        )

    def test_synthetic_kinds_route_to_their_processor(self):
        # The "synthetic" source kinds (live API flags + research) are not
        # in ALLOWED_EXTENSIONS because they are not uploaded as files, but
        # the pipeline still has to know how to process them when their
        # upload helpers create the metadata file.
        m = SourcePipeline.PROCESSOR_MAP
        assert m[".database"] == "database"
        assert m[".freshdesk"] == "freshdesk"
        assert m[".jira"] == "jira"
        assert m[".mixpanel"] == "mixpanel"
        assert m[".mcp"] == "mcp"
        assert m[".research"] == "research"

    def test_link_extension_dispatches_to_link_processor(self):
        # `.link` covers both website URL and YouTube; the pipeline
        # dispatcher delegates the URL/YouTube split to the link processor.
        assert SourcePipeline.PROCESSOR_MAP[".link"] == "link"


# ---------------------------------------------------------------------------
# SourcePipeline.process_source error paths
# ---------------------------------------------------------------------------


class TestProcessSourceErrorPaths:
    """Pin the structured-error contract for ``process_source``.

    These are the two early-exit branches the orchestrator owns before any
    processor runs. They have to stay structured-error so the background
    task scheduler does not re-queue silently.
    """

    def test_missing_source_returns_structured_error(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service:
            mock_service.get_source.return_value = None

            result = pipeline.process_source(PROJECT_ID, SOURCE_ID)

        assert result == {"success": False, "error": "Source not found"}

    def test_missing_stored_filename_returns_structured_error(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service:
            mock_service.get_source.return_value = {
                "id": SOURCE_ID,
                "status": "uploaded",
                # Empty embedding_info — upload never recorded the stored filename.
                "embedding_info": {"file_extension": ".pdf"},
            }

            result = pipeline.process_source(PROJECT_ID, SOURCE_ID)

        assert result == {
            "success": False,
            "error": "Source has no stored filename",
        }
        # The early-exit branch must NOT mark the source as processing —
        # otherwise a stuck source can never be retried because retry only
        # accepts non-ready statuses but `process_source` would have flipped
        # it to "processing" before failing.
        mock_service.update_source.assert_not_called()


# ---------------------------------------------------------------------------
# SourcePipeline.cancel_processing / retry_processing
# ---------------------------------------------------------------------------


class TestCancelProcessing:

    @pytest.mark.parametrize("terminal_status", ["ready", "error"])
    def test_terminal_status_is_no_op(self, terminal_status):
        # Cancelling a finished source must not delete its processed file
        # or chunks — that would silently corrupt a working source.
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service, patch(
            "app.background.tasks.task_service"
        ) as mock_tasks, patch(
            "app.sources.pipeline.storage_service"
        ) as mock_storage:
            mock_service.get_source.return_value = {
                "id": SOURCE_ID,
                "status": terminal_status,
            }

            assert pipeline.cancel_processing(PROJECT_ID, SOURCE_ID) is False

            mock_tasks.cancel_tasks_for_target.assert_not_called()
            mock_storage.delete_processed_file.assert_not_called()
            mock_storage.delete_source_chunks.assert_not_called()
            mock_service.update_source.assert_not_called()

    def test_missing_source_returns_false(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service:
            mock_service.get_source.return_value = None

            assert pipeline.cancel_processing(PROJECT_ID, SOURCE_ID) is False

    @pytest.mark.parametrize(
        "active_status", ["uploaded", "processing", "embedding"]
    )
    def test_active_status_cancels(self, active_status):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service, patch(
            "app.background.tasks.task_service"
        ) as mock_tasks, patch(
            "app.sources.pipeline.storage_service"
        ) as mock_storage:
            mock_service.get_source.return_value = {
                "id": SOURCE_ID,
                "status": active_status,
            }
            mock_tasks.cancel_tasks_for_target.return_value = 1

            assert pipeline.cancel_processing(PROJECT_ID, SOURCE_ID) is True

            mock_tasks.cancel_tasks_for_target.assert_called_once_with(SOURCE_ID)
            mock_storage.delete_processed_file.assert_called_once_with(
                PROJECT_ID, SOURCE_ID
            )
            mock_storage.delete_source_chunks.assert_called_once_with(
                PROJECT_ID, SOURCE_ID
            )
            mock_service.update_source.assert_called_once()
            # Status is reset to "uploaded" so the user can retry.
            assert (
                mock_service.update_source.call_args.kwargs["status"]
                == "uploaded"
            )


class TestRetryProcessing:

    def test_already_ready_refuses(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service:
            mock_service.get_source.return_value = {
                "id": SOURCE_ID,
                "status": "ready",
            }
            result = pipeline.retry_processing(PROJECT_ID, SOURCE_ID)

        assert result == {
            "success": False,
            "error": "Source is already processed",
        }

    def test_missing_source_returns_structured_error(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service:
            mock_service.get_source.return_value = None
            result = pipeline.retry_processing(PROJECT_ID, SOURCE_ID)

        assert result == {"success": False, "error": "Source not found"}

    def test_missing_stored_filename_refuses(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service, patch(
            "app.background.tasks.task_service"
        ):
            mock_service.get_source.return_value = {
                "id": SOURCE_ID,
                "status": "error",
                "embedding_info": {},
            }
            result = pipeline.retry_processing(PROJECT_ID, SOURCE_ID)

        assert result == {
            "success": False,
            "error": "Source has no stored filename",
        }

    def test_missing_raw_file_in_storage_refuses(self):
        pipeline = SourcePipeline()

        with patch(
            "app.services.source_services.source_service"
        ) as mock_service, patch(
            "app.background.tasks.task_service"
        ), patch(
            "app.sources.pipeline.storage_service"
        ) as mock_storage:
            mock_service.get_source.return_value = {
                "id": SOURCE_ID,
                "status": "error",
                "embedding_info": {"stored_filename": "src.pdf"},
            }
            mock_storage.download_raw_file.return_value = None

            result = pipeline.retry_processing(PROJECT_ID, SOURCE_ID)

        assert result == {
            "success": False,
            "error": "Raw file not found in storage",
        }


# ---------------------------------------------------------------------------
# SourceCatalog summary surface
# ---------------------------------------------------------------------------


class TestSourcesSummary:
    """``get_sources_summary`` is what the Sources panel header renders.

    The two invariants below pin the envelope shape so the frontend never
    sees a missing ``by_category`` / ``by_status`` key after migration.
    """

    def test_empty_project_returns_zeroed_envelope(self, monkeypatch):
        monkeypatch.setattr(
            "app.sources.catalog.index.list_sources_from_index",
            lambda project_id: [],
        )

        summary = SourceCatalog().get_sources_summary(PROJECT_ID)

        assert summary == {
            "total_count": 0,
            "total_size": 0,
            "by_category": {},
            "by_status": {},
        }

    def test_buckets_aggregate_by_category_and_status(self, monkeypatch):
        sources = [
            {"category": "document", "status": "ready", "file_size": 100},
            {"category": "document", "status": "ready", "file_size": 50},
            {"category": "image", "status": "processing", "file_size": 25},
            # Missing fields exercise the unknown-bucket fallback.
            {"file_size": 10},
        ]
        monkeypatch.setattr(
            "app.sources.catalog.index.list_sources_from_index",
            lambda project_id: sources,
        )

        summary = SourceCatalog().get_sources_summary(PROJECT_ID)

        assert summary["total_count"] == 4
        assert summary["total_size"] == 185
        assert summary["by_category"] == {
            "document": 2,
            "image": 1,
            "unknown": 1,
        }
        assert summary["by_status"] == {
            "ready": 2,
            "processing": 1,
            "unknown": 1,
        }

    def test_get_allowed_extensions_returns_a_copy(self, monkeypatch):
        # The catalog hands the upload UI a copy of the contract — mutating
        # the returned dict must not change subsequent calls. This is the
        # reason the catalog goes through `ALLOWED_EXTENSIONS.copy()` rather
        # than returning the module-level dict directly.
        catalog = SourceCatalog()
        allowed = catalog.get_allowed_extensions()
        allowed["bogus"] = "bogus"
        assert "bogus" not in catalog.get_allowed_extensions()
