"""
Embedding pipeline orchestration.

Coordinates the embedding workflow for any source type that produces
processed text:

1. Check if source needs embedding (token count > threshold).
2. Parse processed text into chunks (one page = one chunk).
3. Upload chunks to Supabase Storage.
4. Create embeddings via OpenAI.
5. Upsert vectors to Pinecone.

Called after source processing (e.g. PDF extraction) completes.

Module-level form: the previous `EmbeddingService` class held no state
(`__init__` was `pass`); NBB-706 collapses it into module functions.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.providers.openai import embeddings as openai_embeddings
from app.providers.pinecone import pinecone_service
from app.providers.supabase import storage_service
from app.sources.tokens import needs_embedding
from app.sources.text import (
    clean_text_for_embedding,
    chunks_to_pinecone_format,
    parse_extracted_text,
)

logger = logging.getLogger(__name__)


def process_embeddings(
    project_id: str,
    source_id: str,
    source_name: str,
    processed_text: str,
) -> Dict[str, Any]:
    """Run the full embedding pipeline for one source.

    Returns embedding_info with `is_embedded`, `embedded_at`, `token_count`,
    `chunk_count`, and `reason`.
    """
    should_embed, token_count, reason = needs_embedding(text=processed_text)
    logger.info("Embedding check for %s: %s", source_name, reason)

    if not should_embed:
        return {
            "is_embedded": False,
            "embedded_at": None,
            "token_count": token_count,
            "chunk_count": 0,
            "reason": reason,
        }

    if not pinecone_service.is_configured():
        return {
            "is_embedded": False,
            "embedded_at": None,
            "token_count": token_count,
            "chunk_count": 0,
            "reason": "Pinecone not configured - embedding skipped",
        }

    try:
        chunks = parse_extracted_text(
            text=processed_text,
            source_id=source_id,
            source_name=source_name,
        )
        if not chunks:
            return {
                "is_embedded": False,
                "embedded_at": None,
                "token_count": token_count,
                "chunk_count": 0,
                "reason": "No chunks created from text",
            }

        logger.info("Created %d chunks for %s", len(chunks), source_name)

        owner_user_id = storage_service.get_project_storage_owner_id(project_id)
        uploaded_count = 0
        for chunk in chunks:
            storage_path = storage_service.upload_chunk(
                project_id=project_id,
                source_id=source_id,
                chunk_id=chunk.chunk_id,
                content=chunk.text,
                owner_user_id=owner_user_id,
            )
            if storage_path:
                uploaded_count += 1
        logger.info("Uploaded %d chunks to Supabase Storage", uploaded_count)

        chunk_texts = [clean_text_for_embedding(chunk.text) for chunk in chunks]
        embeddings = openai_embeddings.create_embeddings_batch(chunk_texts)
        logger.info("Created %d embeddings", len(embeddings))

        vectors = chunks_to_pinecone_format(chunks, embeddings)
        upsert_result = pinecone_service.upsert_vectors(
            vectors=vectors,
            namespace=project_id,
        )
        logger.info(
            "Upserted %d vectors to Pinecone",
            upsert_result.get("upserted_count", 0),
        )

        return {
            "is_embedded": True,
            "embedded_at": datetime.now().isoformat(),
            "token_count": token_count,
            "chunk_count": len(chunks),
            "reason": f"Successfully embedded {len(chunks)} chunks",
        }
    except Exception as exc:
        logger.exception("Embedding workflow error")
        return {
            "is_embedded": False,
            "embedded_at": None,
            "token_count": token_count,
            "chunk_count": 0,
            "reason": f"Embedding failed: {exc}",
        }


def delete_embeddings(project_id: str, source_id: str) -> Dict[str, Any]:
    """Delete the source's Pinecone vectors and chunk files."""
    results = {"pinecone_deleted": False, "chunks_deleted": False}

    if pinecone_service.is_configured():
        try:
            pinecone_service.delete_by_source(
                source_id=source_id,
                namespace=project_id,
            )
            results["pinecone_deleted"] = True
        except Exception:
            logger.exception("Error deleting from Pinecone")

    try:
        storage_service.delete_source_chunks(project_id, source_id)
        results["chunks_deleted"] = True
    except Exception:
        logger.exception("Error deleting chunks from Supabase Storage")

    return results


def search_similar(
    project_id: str,
    query_text: str,
    top_k: int = 5,
    source_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """RAG retrieval: embed the query, search Pinecone, attach chunk text."""
    if not pinecone_service.is_configured():
        return []

    try:
        query_embedding = openai_embeddings.create_embedding(
            clean_text_for_embedding(query_text)
        )
        pinecone_filter = (
            {"source_id": {"$eq": source_filter}} if source_filter else None
        )
        search_results = pinecone_service.search(
            query_vector=query_embedding,
            namespace=project_id,
            top_k=top_k,
            filter=pinecone_filter,
        )

        enriched_results: List[Dict[str, Any]] = []
        for result in search_results:
            chunk_id = result.get("id")
            source_id = result.get("metadata", {}).get("source_id")
            chunk_text = None
            if source_id and chunk_id:
                chunk_text = storage_service.download_chunk(
                    project_id=project_id,
                    source_id=source_id,
                    chunk_id=chunk_id,
                )
            enriched_result = {
                "chunk_id": chunk_id,
                "score": result.get("score"),
                "source_id": source_id,
                "source_name": result.get("metadata", {}).get("source_name"),
                "page_number": result.get("metadata", {}).get("page_number"),
            }
            if chunk_text:
                enriched_result["text"] = chunk_text
            else:
                enriched_result["text"] = result.get("metadata", {}).get("text")
            enriched_results.append(enriched_result)

        return enriched_results
    except Exception:
        logger.exception("Search error")
        return []
