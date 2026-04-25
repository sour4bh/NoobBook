"""
Citation lookup and route tests (NBB-702).

Coverage delta over `tests/test_citation_utils.py` (which already pins
`parse_chunk_id` and `extract_citations_from_text`):

- `get_chunk_content` — happy path, missing chunk, malformed chunk_id, missing
  source row.
- `get_multiple_chunks` — only found chunks are returned (silently drops
  misses).
- `get_citations_with_content` — extract + fetch in one call, dedupes via the
  underlying extraction.
- Route `GET /api/v1/projects/<project_id>/citations/<chunk_id>` — 200, 404,
  500. The route is the consumer that the chat frontend hovers fire against,
  so its envelope shape is load-bearing.
"""
import pytest

from app.sources import citations as citations_module

from tests.sources.conftest import PROJECT_ID, SOURCE_ID


CHUNK_ID = f"{SOURCE_ID}_page_5_chunk_2"


# ---------------------------------------------------------------------------
# get_chunk_content
# ---------------------------------------------------------------------------


class TestGetChunkContent:

    def test_happy_path_returns_full_envelope(self, monkeypatch):
        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk",
            lambda project_id, source_id, chunk_id: "Revenue increased 15% in Q3.",
        )
        monkeypatch.setattr(
            "app.sources.citations.index.get_source_from_index",
            lambda project_id, source_id: {
                "id": source_id,
                "name": "Q3 Financial Report.pdf",
            },
        )

        result = citations_module.get_chunk_content(PROJECT_ID, CHUNK_ID)

        assert result == {
            "content": "Revenue increased 15% in Q3.",
            "chunk_id": CHUNK_ID,
            "source_id": SOURCE_ID,
            "source_name": "Q3 Financial Report.pdf",
            "page_number": 5,
            "chunk_index": 2,
        }

    def test_returns_unknown_when_source_row_missing(self, monkeypatch):
        # Storage has the chunk text but the source row was deleted; the
        # endpoint must still return the chunk content (so the user sees
        # something) and degrade source_name to "Unknown" — never crash.
        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk",
            lambda project_id, source_id, chunk_id: "Some text.",
        )
        monkeypatch.setattr(
            "app.sources.citations.index.get_source_from_index",
            lambda project_id, source_id: None,
        )

        result = citations_module.get_chunk_content(PROJECT_ID, CHUNK_ID)

        assert result is not None
        assert result["source_name"] == "Unknown"
        assert result["content"] == "Some text."

    def test_malformed_chunk_id_returns_none(self, monkeypatch):
        # parse_chunk_id rejects malformed IDs before any storage call.
        # Pin that the storage call never fires for a bad ID — otherwise a
        # citation tooltip could leak storage-not-found errors for
        # arbitrary user input.
        called = {"download": 0, "lookup": 0}

        def fake_download(*args, **kwargs):
            called["download"] += 1
            return "should-not-run"

        def fake_lookup(*args, **kwargs):
            called["lookup"] += 1
            return None

        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk", fake_download
        )
        monkeypatch.setattr(
            "app.sources.citations.index.get_source_from_index", fake_lookup
        )

        assert citations_module.get_chunk_content(PROJECT_ID, "not-a-chunk-id") is None
        assert called == {"download": 0, "lookup": 0}

    def test_storage_miss_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk",
            lambda project_id, source_id, chunk_id: None,
        )
        # Lookup must NOT run when the chunk is missing; otherwise we waste a
        # DB round-trip on every dead-link tooltip.
        monkeypatch.setattr(
            "app.sources.citations.index.get_source_from_index",
            lambda project_id, source_id: pytest.fail(
                "get_source_from_index should not run when storage misses"
            ),
        )

        assert citations_module.get_chunk_content(PROJECT_ID, CHUNK_ID) is None


# ---------------------------------------------------------------------------
# get_multiple_chunks
# ---------------------------------------------------------------------------


class TestGetMultipleChunks:

    def test_drops_missing_chunks_silently(self, monkeypatch):
        # Two chunk_ids; first is found, second misses storage. The result
        # list should contain only the found chunk — never None entries —
        # so the frontend never has to filter sentinels.
        found_id = f"{SOURCE_ID}_page_1_chunk_1"
        missing_id = f"{SOURCE_ID}_page_9_chunk_9"

        def fake_download(project_id, source_id, chunk_id):
            return "found content" if chunk_id == found_id else None

        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk", fake_download
        )
        monkeypatch.setattr(
            "app.sources.citations.index.get_source_from_index",
            lambda project_id, source_id: {"id": source_id, "name": "doc.pdf"},
        )

        result = citations_module.get_multiple_chunks(
            PROJECT_ID, [found_id, missing_id]
        )

        assert len(result) == 1
        assert result[0]["chunk_id"] == found_id

    def test_empty_chunk_id_list_returns_empty(self, monkeypatch):
        # Lookups must never fire on empty input; any call would imply the
        # function was iterating a default rather than the argument.
        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk",
            lambda *a, **kw: pytest.fail("download_chunk should not run"),
        )
        assert citations_module.get_multiple_chunks(PROJECT_ID, []) == []


# ---------------------------------------------------------------------------
# get_citations_with_content
# ---------------------------------------------------------------------------


class TestGetCitationsWithContent:

    def test_extracts_and_fetches_unique_chunks(self, monkeypatch):
        # Two distinct chunks plus a duplicate marker. Underlying extraction
        # dedupes; this test pins that the dedupe shows up in fetch results
        # too (each chunk fetched exactly once).
        chunk_a = f"{SOURCE_ID}_page_1_chunk_1"
        chunk_b = f"{SOURCE_ID}_page_2_chunk_5"
        text = (
            f"First [[cite:{chunk_a}]] and again [[cite:{chunk_a}]] "
            f"and second [[cite:{chunk_b}]]."
        )

        downloads = []

        def fake_download(project_id, source_id, chunk_id):
            downloads.append(chunk_id)
            return f"content for {chunk_id}"

        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk", fake_download
        )
        monkeypatch.setattr(
            "app.sources.citations.index.get_source_from_index",
            lambda project_id, source_id: {"id": source_id, "name": "doc.pdf"},
        )

        result = citations_module.get_citations_with_content(PROJECT_ID, text)

        assert set(result.keys()) == {chunk_a, chunk_b}
        # Dedupe pin: each chunk hit storage exactly once.
        assert sorted(downloads) == sorted([chunk_a, chunk_b])
        assert result[chunk_a]["content"] == f"content for {chunk_a}"

    def test_text_without_citations_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "app.sources.citations.storage_service.download_chunk",
            lambda *a, **kw: pytest.fail("download_chunk should not run"),
        )
        assert citations_module.get_citations_with_content(
            PROJECT_ID, "no markers here"
        ) == {}


# ---------------------------------------------------------------------------
# Route: GET /api/v1/projects/<project_id>/citations/<chunk_id>
# ---------------------------------------------------------------------------


class TestCitationRoute:

    URL_TEMPLATE = "/api/v1/projects/{project_id}/citations/{chunk_id}"

    def _url(self, chunk_id=CHUNK_ID):
        return self.URL_TEMPLATE.format(project_id=PROJECT_ID, chunk_id=chunk_id)

    def test_returns_200_with_chunk_envelope(
        self, sources_client, monkeypatch, bypass_project_access
    ):
        monkeypatch.setattr(
            "app.api.sources.content.get_chunk_content",
            lambda project_id, chunk_id: {
                "content": "Cited text.",
                "chunk_id": chunk_id,
                "source_id": SOURCE_ID,
                "source_name": "doc.pdf",
                "page_number": 5,
                "chunk_index": 2,
            },
        )

        response = sources_client.get(self._url())

        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["chunk"] == {
            "content": "Cited text.",
            "chunk_id": CHUNK_ID,
            "source_id": SOURCE_ID,
            "source_name": "doc.pdf",
            "page_number": 5,
            "chunk_index": 2,
        }

    def test_returns_404_when_chunk_missing(
        self, sources_client, monkeypatch, bypass_project_access
    ):
        monkeypatch.setattr(
            "app.api.sources.content.get_chunk_content",
            lambda project_id, chunk_id: None,
        )

        response = sources_client.get(self._url())

        assert response.status_code == 404
        body = response.get_json()
        assert body["success"] is False
        assert CHUNK_ID in body["error"]

    def test_returns_500_when_lookup_raises(
        self, sources_client, monkeypatch, bypass_project_access
    ):
        # The route wraps its lookup in try/except. A storage outage that
        # raises (rather than returning None) must surface as 500 with a
        # JSON envelope — never bleed a Flask HTML 500 page.
        def boom(project_id, chunk_id):
            raise RuntimeError("storage unreachable")

        monkeypatch.setattr(
            "app.api.sources.content.get_chunk_content", boom
        )

        response = sources_client.get(self._url())

        assert response.status_code == 500
        body = response.get_json()
        assert body["success"] is False
        assert "storage unreachable" in body["error"]
