"""
Anthropic response parsing.

Predicates and extractors over the raw response shape returned by
``claude_service.send_message()``. Covers stop-reason checks, text
and citation extraction, and both client-tool and server-tool block
extraction. Content-block construction lives in ``content.py``;
token/model accessors live in ``usage.py``.
"""
from typing import Dict, Any, List, Optional


def has_server_tool_use(response: Dict[str, Any]) -> bool:
    """
    Check if response contains server tool usage.

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        True if response contains server_tool_use blocks
    """
    return len(extract_server_tool_use_blocks(response)) > 0


def extract_server_tool_results(
    response: Dict[str, Any],
    result_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract server tool result blocks from Claude response.

    Educational Note: Server tool results have types like:
    - "web_search_tool_result" - Results from web_search
    - "web_fetch_tool_result" - Results from web_fetch

    These results are included directly in Claude's response and don't
    require us to send tool_result messages back.

    Args:
        response: Response dict from claude_service.send_message()
        result_type: Optional filter - "web_search_tool_result" or "web_fetch_tool_result"

    Returns:
        List of dicts: [{type, tool_use_id, content}, ...]
    """
    result_blocks = []
    content_blocks = response.get("content_blocks", [])

    # Types we recognize as server tool results
    server_result_types = {"web_search_tool_result", "web_fetch_tool_result"}

    for block in content_blocks:
        block_type = getattr(block, "type", None) if hasattr(block, "type") else block.get("type")

        if block_type in server_result_types:
            if result_type is None or block_type == result_type:
                result_blocks.append({
                    "type": block_type,
                    "tool_use_id": getattr(block, "tool_use_id", None) if hasattr(block, "tool_use_id") else block.get("tool_use_id"),
                    "content": getattr(block, "content", None) if hasattr(block, "content") else block.get("content"),
                })

    return result_blocks


def extract_server_tool_use_blocks(
    response: Dict[str, Any],
    tool_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract server_tool_use blocks from Claude response.

    Educational Note: Server tools (web_search, web_fetch) are executed by Claude
    directly. They appear as "server_tool_use" blocks, and their results come
    back in the same response as "*_tool_result" blocks.

    Args:
        response: Response dict from claude_service.send_message()
        tool_name: Optional filter - only return blocks for this tool

    Returns:
        List of dicts: [{id, name, input}, ...]
    """
    tool_blocks = []
    content_blocks = response.get("content_blocks", [])

    for block in content_blocks:
        # Handle Anthropic objects
        if hasattr(block, 'type') and block.type == "server_tool_use":
            if tool_name is None or block.name == tool_name:
                tool_blocks.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        # Handle dict format
        elif isinstance(block, dict) and block.get("type") == "server_tool_use":
            if tool_name is None or block.get("name") == tool_name:
                tool_blocks.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                })

    return tool_blocks


def extract_tool_inputs(
    response: Dict[str, Any],
    tool_name: str
) -> List[Dict[str, Any]]:
    """
    Extract just the input parameters from tool_use blocks.

    Educational Note: Convenience method when you only need the inputs
    (not the IDs). Useful for extraction tasks like PDF processing where
    Claude uses submit_page_extraction tool and you just want the data.

    Args:
        response: Response dict from claude_service.send_message()
        tool_name: Name of the tool to extract inputs for

    Returns:
        List of input dicts from matching tool_use blocks
    """
    tool_blocks = extract_tool_use_blocks(response, tool_name)
    return [block["input"] for block in tool_blocks]


def extract_tool_use_blocks(
    response: Dict[str, Any],
    tool_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract tool_use blocks from Claude response.

    Educational Note: Claude can call multiple tools in parallel. Each tool_use has:
    - id: Unique identifier (e.g., "toolu_01") - MUST match in tool_result
    - name: Tool being called
    - input: Parameters for the tool

    Args:
        response: Response dict from claude_service.send_message()
        tool_name: Optional filter - only return blocks for this tool

    Returns:
        List of dicts: [{id, name, input}, ...]
    """
    tool_blocks = []
    content_blocks = response.get("content_blocks", [])

    for block in content_blocks:
        # Handle Anthropic objects (have .type attribute)
        if hasattr(block, 'type') and block.type == "tool_use":
            if tool_name is None or block.name == tool_name:
                tool_blocks.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        # Handle dict format (already serialized)
        elif isinstance(block, dict) and block.get("type") == "tool_use":
            if tool_name is None or block.get("name") == tool_name:
                tool_blocks.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                })

    return tool_blocks


def extract_text_with_citations(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract both text and citations from Claude response.

    Educational Note: Convenience method that returns both the text content
    and any citations from web_search. Useful for research agents that need
    to cite their sources.

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        Dict with 'text' and 'citations' keys
    """
    return {
        "text": extract_text(response),
        "citations": extract_citations(response)
    }


def extract_citations(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract citations from web_search text blocks.

    Educational Note: When Claude uses web_search, text blocks can include
    citations with the source information. Each citation contains:
    - url: The source URL
    - title: The page title
    - encrypted_index: Reference for multi-turn (we can ignore)
    - cited_text: Up to 150 chars of the cited content

    This is valuable for the research agent to properly cite sources!

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        List of citation dicts: [{url, title, cited_text}, ...]
    """
    citations = []
    content_blocks = response.get("content_blocks", [])

    for block in content_blocks:
        block_citations = None

        # Handle Anthropic objects
        if hasattr(block, 'type') and block.type == "text":
            block_citations = getattr(block, 'citations', None)
        # Handle dict format
        elif isinstance(block, dict) and block.get("type") == "text":
            block_citations = block.get("citations")

        if block_citations:
            for citation in block_citations:
                # Extract the useful fields (skip encrypted_index)
                if hasattr(citation, 'url'):
                    citations.append({
                        "url": citation.url,
                        "title": getattr(citation, 'title', ''),
                        "cited_text": getattr(citation, 'cited_text', '')
                    })
                elif isinstance(citation, dict):
                    citations.append({
                        "url": citation.get("url", ""),
                        "title": citation.get("title", ""),
                        "cited_text": citation.get("cited_text", "")
                    })

    return citations


def extract_text(response: Dict[str, Any]) -> str:
    """
    Extract text content from Claude response.

    Educational Note: Response content_blocks can contain multiple blocks
    (text + tool_use). This extracts only the text portions.
    For tool_use responses, this gets Claude's explanation like
    "I'll check the weather for you."

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        Combined text content as a single string
    """
    content_blocks = response.get("content_blocks", [])
    text_parts = []

    for block in content_blocks:
        # Handle Anthropic objects (have .type attribute)
        if hasattr(block, 'type') and block.type == "text":
            text_parts.append(block.text)
        # Handle dict format (already serialized)
        elif isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    return "\n".join(text_parts)


def get_stop_reason(response: Dict[str, Any]) -> str:
    """
    Get the stop_reason from response.

    Common values:
    - "end_turn": Claude finished (final text response)
    - "tool_use": Claude wants to use tools
    - "max_tokens": Response truncated
    - "stop_sequence": Hit a stop sequence

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        The stop_reason string
    """
    return response.get("stop_reason", "")


def is_tool_use(response: Dict[str, Any]) -> bool:
    """
    Check if response contains tool_use blocks that need tool_result back.

    Educational Note: When stop_reason is "tool_use", we must:
    1. Extract all tool_use blocks
    2. Execute each tool
    3. Send back tool_result for each (with matching IDs)
    4. Call Claude again to continue

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        True if stop_reason is "tool_use"
    """
    return response.get("stop_reason") == "tool_use"


def is_end_turn(response: Dict[str, Any]) -> bool:
    """
    Check if response is a final text response (conversation complete).

    Args:
        response: Response dict from claude_service.send_message()

    Returns:
        True if stop_reason is "end_turn"
    """
    return response.get("stop_reason") == "end_turn"
