"""
Anthropic response usage and model accessors.

Token-count and model fields live here so chat and orchestration
code can read them without pulling in cost-tracking helpers from
``cost.py``.
"""
from typing import Dict, Any


def get_model(response: Dict[str, Any]) -> str:
    """
    Get the model name from response.

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        Model string (e.g., "claude-sonnet-4-6")
    """
    return response.get("model", "")


def get_token_usage(response: Dict[str, Any]) -> Dict[str, int]:
    """
    Extract token usage from response.

    Educational Note: Token usage is important for:
    - Cost tracking (Sonnet: $3/$15, Haiku: $1/$5 per 1M tokens)
    - Debugging context length issues
    - Optimizing prompt sizes

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        Dict with 'input_tokens' and 'output_tokens'
    """
    usage = response.get("usage", {})
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }
