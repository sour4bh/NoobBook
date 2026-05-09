from app.sources.search import SourceSearchExecutor


def test_large_source_query_falls_back_to_local_chunks_when_semantic_is_empty(
    monkeypatch,
) -> None:
    executor = SourceSearchExecutor()
    chunks = [
        {
            "chunk_id": "source-1_page_1_chunk_1",
            "text": "First chunk content",
            "page_number": 1,
            "source_id": "source-1",
        },
        {
            "chunk_id": "source-1_page_2_chunk_1",
            "text": "Second chunk content",
            "page_number": 2,
            "source_id": "source-1",
        },
    ]
    monkeypatch.setattr(
        "app.sources.search.storage_service.list_source_chunks",
        lambda project_id, source_id: chunks,
    )
    monkeypatch.setattr(
        executor,
        "_semantic_search",
        lambda project_id, source_id, query: [],
    )

    result = executor._search_large_source(
        project_id="project-1",
        source_id="source-1",
        source={"name": "Notes"},
        keywords=None,
        query="semantic question",
    )

    assert result["success"] is True
    assert result["matches"] == 2
    assert "No matching content found" not in result["content"]
    assert "source-1_page_1_chunk_1" in result["content"]
