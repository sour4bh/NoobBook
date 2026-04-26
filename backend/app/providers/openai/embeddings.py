"""
OpenAI embeddings.

Module-level wrapper around the OpenAI embeddings API. The previous class
form held no per-instance state — `_client` was always the only attribute
— so NBB-706 collapses it into module functions with a lazy module-private
`_client` cache.

OpenAI embedding models:
- text-embedding-3-small: 1536 dimensions, cheaper, default for NoobBook.
- text-embedding-3-large: 3072 dimensions, more accurate, more expensive.
- text-embedding-ada-002: legacy, 1536 dimensions.
"""
import os
from typing import List, Optional

from openai import OpenAI

from app.utils.text import clean_text_for_embedding

DEFAULT_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

_DIMENSIONS_BY_MODEL = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Return the cached OpenAI client, building it lazily on first use."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        _client = OpenAI(api_key=api_key)
    return _client


def create_embedding(text: str, model: str = DEFAULT_MODEL) -> List[float]:
    """Create a single embedding vector for `text`.

    Empty text raises `ValueError`. Text is cleaned via
    `clean_text_for_embedding` before sending.
    """
    clean_text = clean_text_for_embedding(text)
    if not clean_text:
        raise ValueError("Cannot create embedding for empty text")
    client = _get_client()
    response = client.embeddings.create(model=model, input=clean_text)
    return response.data[0].embedding


def create_embeddings_batch(
    texts: List[str],
    model: str = DEFAULT_MODEL,
) -> List[List[float]]:
    """Create embeddings for `texts` in a single batched API call.

    Each text is cleaned; empty cleaned texts are replaced with a zero
    vector of `EMBEDDING_DIMENSIONS` length so the output list matches
    the input length and order. OpenAI supports up to 2048 texts per
    batch request.
    """
    if not texts:
        return []

    cleaned_texts: List[str] = []
    valid_indices: List[int] = []
    for i, text in enumerate(texts):
        clean = clean_text_for_embedding(text)
        if clean:
            cleaned_texts.append(clean)
            valid_indices.append(i)

    if not cleaned_texts:
        raise ValueError("All texts are empty after cleaning")

    client = _get_client()
    response = client.embeddings.create(model=model, input=cleaned_texts)

    embeddings_map = {item.index: item.embedding for item in response.data}
    valid_embeddings = [embeddings_map[i] for i in range(len(cleaned_texts))]

    result: List[Optional[List[float]]] = [None] * len(texts)
    for orig_idx, embedding in zip(valid_indices, valid_embeddings):
        result[orig_idx] = embedding
    for i, emb in enumerate(result):
        if emb is None:
            result[i] = [0.0] * EMBEDDING_DIMENSIONS
    return result  # type: ignore[return-value]


def get_embedding_dimensions(model: str = DEFAULT_MODEL) -> int:
    """Return the number of dimensions for `model` (defaults to 1536)."""
    return _DIMENSIONS_BY_MODEL.get(model, 1536)
