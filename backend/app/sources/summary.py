"""
Source summary generation.

Generates summaries for source documents after processing completes. Uses
a smart sampling strategy to handle documents of varying sizes while
keeping API costs low.

Strategy:
- Small sources (not chunked, <2500 tokens): send entire content.
- Large sources (chunked): send 8 evenly distributed chunks.
- Output: 150-200 tokens via Haiku.

Module-level form: the previous `SummaryService` class held only a lazy
`_prompt_config` cache; NBB-706 collapses it into module functions and
preserves the cache as a module-private variable.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    run_with_provider,
)
from app.config.prompt import render_prompt
from app.providers.supabase import storage_service

logger = logging.getLogger(__name__)

# Maximum chunks to send for summarization (budget: ~20k tokens).
MAX_CHUNKS = 8

def _get_chunk_indices(total_chunks: int, chunks_to_select: int) -> List[int]:
    """Evenly distributed chunk indices, always including first and last."""
    if chunks_to_select >= total_chunks:
        return list(range(total_chunks))
    if chunks_to_select == 1:
        return [0]
    if chunks_to_select == 2:
        return [0, total_chunks - 1]
    step = (total_chunks - 1) / (chunks_to_select - 1)
    return [round(i * step) for i in range(chunks_to_select)]


def _load_processed_content(project_id: str, source_id: str) -> Optional[str]:
    """Load the full processed content for a source from Supabase Storage."""
    return storage_service.download_processed_file(project_id, source_id)


def _load_selected_chunks(project_id: str, source_id: str) -> Optional[str]:
    """Load evenly distributed chunks and concatenate them."""
    all_chunks = storage_service.list_source_chunks(project_id, source_id)
    if not all_chunks:
        return None
    chunks_to_select = min(MAX_CHUNKS, len(all_chunks))
    indices = _get_chunk_indices(len(all_chunks), chunks_to_select)
    content_parts: List[str] = []
    for idx in indices:
        if idx < len(all_chunks):
            chunk = all_chunks[idx]
            page_num = chunk.get("page_number", idx + 1)
            content_parts.append(f"[Page {page_num}]\n{chunk['text']}")
    return "\n\n---\n\n".join(content_parts)


def _summary_context(
    content: str,
    source_metadata: Dict[str, Any],
    is_sampled: bool,
    total_pages: int,
    pages_sent: int,
) -> Dict[str, Any]:
    """Build the prompt render context for source summaries."""
    category = source_metadata.get("category", "document")
    name = source_metadata.get("name", "Unknown")
    file_ext = source_metadata.get("file_extension", "")
    if is_sampled:
        content_info = (
            f"Content Provided: {pages_sent} pages sampled at equal intervals "
            "(pages include beginning, end, and evenly distributed middle sections)"
        )
    else:
        content_info = f"Content Provided: Full document ({pages_sent} pages)"
    return {
        "document_type": category.upper(),
        "file_extension": file_ext,
        "document_name": name,
        "total_pages": total_pages,
        "content_info": content_info,
        "content": content,
    }


def generate_summary(
    project_id: str,
    source_id: str,
    source_metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Generate a summary for a processed source.

    Returns the summary dict (`summary`, `model`, `usage`, `generated_at`,
    `strategy`, `pages_used`, `total_pages`) or `None` on failure.
    """
    embedding_info = source_metadata.get("embedding_info", {})
    is_embedded = embedding_info.get("is_embedded", False)
    chunk_count = embedding_info.get("chunk_count", 0)

    processing_info = source_metadata.get("processing_info", {})
    total_pages = processing_info.get("total_pages", 1)

    if is_embedded and chunk_count > 0:
        content = _load_selected_chunks(project_id, source_id)
        is_sampled = chunk_count > MAX_CHUNKS
        pages_sent = min(MAX_CHUNKS, chunk_count)
    else:
        content = _load_processed_content(project_id, source_id)
        is_sampled = False
        pages_sent = total_pages

    if not content:
        logger.warning("No content found for source %s", source_id[:8])
        return None

    prompt = render_prompt(
        "summary",
        _summary_context(
            content=content,
            source_metadata=source_metadata,
            is_sampled=is_sampled,
            total_pages=total_pages,
            pages_sent=pages_sent,
        ),
        project_id=project_id,
    )

    try:
        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose="source_summary",
                messages=[
                    RunMessage(
                        role="user",
                        content=[TextPart(text=prompt.user_message or "")],
                    )
                ],
                system_prompt=prompt.system_prompt,
                limits=RunLimits(
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
            )
        )
        summary_text = result.text.strip()
        if not summary_text:
            logger.warning("Empty summary returned for source %s", source_id[:8])
            return None
        return {
            "summary": summary_text,
            "model": result.model,
            "usage": result.usage.model_dump(mode="json"),
            "generated_at": datetime.now().isoformat(),
            "strategy": "sampled" if is_sampled else "full",
            "pages_used": pages_sent,
            "total_pages": total_pages,
        }
    except Exception:
        logger.exception("Error generating summary for source %s", source_id[:8])
        return None
