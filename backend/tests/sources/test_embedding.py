from app.sources import embedding


PROCESSED_TEXT = """\
# Extracted from TEXT document: notes.txt
# Type: TEXT
# Total pages: 1
# ---

=== TEXT PAGE 1 of 1 ===

This source contains the browser QA marker source-ui-delta-77.
"""


def test_process_embeddings_stores_chunks_without_pinecone(monkeypatch) -> None:
    uploaded: list[dict] = []

    monkeypatch.setattr(
        embedding.pinecone_service,
        "is_configured",
        lambda project_id=None: False,
    )
    monkeypatch.setattr(
        embedding.storage_service,
        "get_project_storage_owner_id",
        lambda project_id: "owner-1",
    )
    monkeypatch.setattr(
        embedding.storage_service,
        "upload_chunk",
        lambda **kwargs: uploaded.append(kwargs) or f"chunks/{kwargs['chunk_id']}.txt",
    )
    monkeypatch.setattr(
        embedding.openai_embeddings,
        "create_embeddings_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("embedding API should not run without Pinecone")
        ),
    )

    result = embedding.process_embeddings(
        project_id="project-1",
        source_id="source-1",
        source_name="notes.txt",
        processed_text=PROCESSED_TEXT,
    )

    assert result["is_embedded"] is False
    assert result["chunk_count"] == 1
    assert result["vector_count"] == 0
    assert result["reason"] == "Pinecone not configured - vector embedding skipped"
    assert uploaded[0]["chunk_id"] == "source-1_page_1_chunk_1"
    assert "source-ui-delta-77" in uploaded[0]["content"]


def test_process_embeddings_keeps_chunk_metadata_when_vector_embedding_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        embedding.pinecone_service,
        "is_configured",
        lambda project_id=None: True,
    )
    monkeypatch.setattr(
        embedding.storage_service,
        "get_project_storage_owner_id",
        lambda project_id: "owner-1",
    )
    monkeypatch.setattr(
        embedding.storage_service,
        "upload_chunk",
        lambda **kwargs: f"chunks/{kwargs['chunk_id']}.txt",
    )
    monkeypatch.setattr(
        embedding.openai_embeddings,
        "create_embeddings_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("missing key")),
    )

    result = embedding.process_embeddings(
        project_id="project-1",
        source_id="source-1",
        source_name="notes.txt",
        processed_text=PROCESSED_TEXT,
    )

    assert result["is_embedded"] is False
    assert result["chunk_count"] == 1
    assert result["vector_count"] == 0
    assert result["embedding_error"] == "missing key"
    assert result["reason"] == "Embedding failed: missing key"


def test_process_embeddings_fails_before_vector_upsert_when_chunk_upload_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        embedding.pinecone_service,
        "is_configured",
        lambda project_id=None: True,
    )
    monkeypatch.setattr(
        embedding.storage_service,
        "get_project_storage_owner_id",
        lambda project_id: "owner-1",
    )
    monkeypatch.setattr(
        embedding.storage_service,
        "upload_chunk",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        embedding.openai_embeddings,
        "create_embeddings_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("embedding API should not run when chunks are missing")
        ),
    )

    result = embedding.process_embeddings(
        project_id="project-1",
        source_id="source-1",
        source_name="notes.txt",
        processed_text=PROCESSED_TEXT,
    )

    assert result["is_embedded"] is False
    assert result["chunk_count"] == 0
    assert result["vector_count"] == 0
    assert result["reason"] == "Chunk storage failed for 1 of 1 chunks"
    assert result["missing_chunk_ids"] == ["source-1_page_1_chunk_1"]
