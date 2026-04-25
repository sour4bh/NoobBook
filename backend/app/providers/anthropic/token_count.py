"""
Anthropic API token counting.

Educational Note: Use this when you need exact Claude token counts,
such as for billing estimation or quota tracking. For local chunking
operations, use ``count_tokens()`` from ``app.utils.embedding_utils``
which uses tiktoken (fast, local) and is ~10000x faster than this API.
"""
import logging

logger = logging.getLogger(__name__)


def count_tokens_api(text: str) -> int:
    """
    Count tokens using Claude's count_tokens API (accurate but slow).

    Args:
        text: The text to count tokens for

    Returns:
        Exact token count according to Claude's tokenizer
    """
    from app.services.integrations.claude import claude_service
    from app.utils.embedding_utils import count_tokens

    if not text:
        return 0

    messages = [{"role": "user", "content": text}]

    try:
        return claude_service.count_tokens(messages=messages)
    except Exception as e:
        logger.warning("API token counting failed, falling back to tiktoken: %s", e)
        return count_tokens(text)
