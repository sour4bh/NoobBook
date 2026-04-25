"""
Anthropic content-block construction and serialization.

Builders for ``tool_result`` user-message content (paired with the
extractors in ``response_parser.py``) and serializers that convert
SDK content-block objects into JSON-serializable dicts for storage.
"""
from typing import Dict, List, Any


def serialize_content_blocks(content_blocks: List[Any]) -> List[Dict[str, Any]]:
    """
    Convert Anthropic content block objects to JSON-serializable dicts.

    Educational Note: Claude API returns content blocks as Anthropic objects
    with attributes (.type, .text, .id). For storing in JSON files (message
    history, debug logs), we need plain dicts.

    Handles both client tools (tool_use) and server tools (server_tool_use,
    web_search_tool_result, web_fetch_tool_result).

    Args:
        content_blocks: List of Anthropic content block objects

    Returns:
        List of JSON-serializable dicts
    """
    serialized = []

    for block in content_blocks:
        # Handle Anthropic objects
        if hasattr(block, 'type'):
            if block.type == "text":
                text_block = {
                    "type": "text",
                    "text": block.text
                }
                # Include citations if present (from web_search)
                if hasattr(block, 'citations') and block.citations:
                    text_block["citations"] = [
                        {
                            "url": getattr(c, 'url', ''),
                            "title": getattr(c, 'title', ''),
                            "cited_text": getattr(c, 'cited_text', '')
                        }
                        for c in block.citations
                    ]
                serialized.append(text_block)
            elif block.type == "tool_use":
                # Client tool use - we execute these
                serialized.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
            elif block.type == "tool_result":
                serialized.append({
                    "type": "tool_result",
                    "tool_use_id": getattr(block, 'tool_use_id', ''),
                    "content": getattr(block, 'content', '')
                })
            elif block.type == "server_tool_use":
                # Server tool use - Claude executes these (web_fetch, web_search)
                serialized.append({
                    "type": "server_tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
            elif block.type == "web_search_tool_result":
                # Server tool result from web_search
                # Content is a list of WebSearchResultBlock objects - must serialize recursively
                serialized.append({
                    "type": "web_search_tool_result",
                    "tool_use_id": getattr(block, 'tool_use_id', ''),
                    "content": _serialize_anthropic_object(getattr(block, 'content', None))
                })
            elif block.type == "web_fetch_tool_result":
                # Server tool result from web_fetch
                # Content is a WebFetchResult object with nested Document - must serialize recursively
                serialized.append({
                    "type": "web_fetch_tool_result",
                    "tool_use_id": getattr(block, 'tool_use_id', ''),
                    "content": _serialize_anthropic_object(getattr(block, 'content', None))
                })
        # Already a dict - pass through
        elif isinstance(block, dict):
            serialized.append(block)

    return serialized


def _serialize_anthropic_object(obj: Any) -> Any:
    """
    Recursively convert Anthropic SDK objects to JSON-serializable dicts.

    Educational Note: Anthropic SDK returns objects with attributes (.type, .url, etc.)
    that aren't JSON serializable. This helper recursively converts them to plain dicts.
    Handles nested objects, lists, and primitive types.

    Used for server tool results (web_search_tool_result, web_fetch_tool_result)
    which contain nested SDK objects like WebSearchResultBlock, WebFetchResult, etc.
    """
    # Already a primitive type - return as-is
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # List - recursively serialize each element
    if isinstance(obj, list):
        return [_serialize_anthropic_object(item) for item in obj]

    # Dict - recursively serialize values
    if isinstance(obj, dict):
        return {key: _serialize_anthropic_object(value) for key, value in obj.items()}

    # Anthropic SDK object - convert to dict by extracting attributes
    if hasattr(obj, '__dict__'):
        result = {}
        for key, value in vars(obj).items():
            # Skip private attributes
            if not key.startswith('_'):
                result[key] = _serialize_anthropic_object(value)
        return result

    # Fallback - try to convert to string
    return str(obj)


def build_single_tool_result(
    tool_use_id: str,
    result: str,
    is_error: bool = False
) -> List[Dict[str, Any]]:
    """
    Build tool_result content for a single tool call.

    Educational Note: Convenience method for the common case of responding
    to a single tool use (non-parallel).

    Args:
        tool_use_id: ID from the tool_use block
        result: The result string
        is_error: Whether tool execution failed

    Returns:
        List with single tool_result content block
    """
    return build_tool_result_content([{
        "tool_use_id": tool_use_id,
        "result": result,
        "is_error": is_error,
    }])


def build_tool_result_content(
    tool_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Build tool_result content blocks for responding to tool_use.

    Educational Note: After Claude calls tools, we send back a single user message
    with ALL tool_result blocks. Each tool_result must have tool_use_id matching
    the original tool_use block.

    Example input:
        [
            {"tool_use_id": "toolu_01", "result": "68°F sunny"},
            {"tool_use_id": "toolu_02", "result": "2:30 PM PST"},
        ]

    Example output:
        [
            {"type": "tool_result", "tool_use_id": "toolu_01", "content": "68°F sunny"},
            {"type": "tool_result", "tool_use_id": "toolu_02", "content": "2:30 PM PST"},
        ]

    Args:
        tool_results: List of dicts with:
            - tool_use_id: ID from the tool_use block (REQUIRED)
            - result: The result string/content
            - is_error: (optional) Whether tool execution failed

    Returns:
        List of tool_result content blocks for user message
    """
    content_blocks = []

    for result in tool_results:
        tool_use_id = result.get("tool_use_id")
        result_content = result.get("result", "")
        is_error = result.get("is_error", False)

        # Ensure result is a string
        if not isinstance(result_content, str):
            result_content = str(result_content)

        block = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result_content,
        }

        # Only add is_error if True (cleaner JSON)
        if is_error:
            block["is_error"] = True

        content_blocks.append(block)

    return content_blocks
