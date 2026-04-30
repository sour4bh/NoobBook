"""
Message Service - Handles message persistence and retrieval for chat conversations.

Educational Note: This is a pure CRUD service for messages using Supabase.
It handles storing and retrieving messages, building message arrays for API calls.

Key Responsibilities:
- Store messages to Supabase messages table
- Retrieve message history
- Build message arrays for the selected model calls
- Support different message types (user, assistant, tool_result)
- Store and retrieve agent execution logs (local files for debugging)

For parsing the selected model responses during the NBB-011 migration, use the
Anthropic adapter boundary in app.providers.anthropic.adapter.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from app.config.runtime import Config
from app.base.paths import get_web_agent_dir, get_agents_dir
from app.agents.runtime import RunMessage
import logging

from app.providers.supabase import get_supabase, is_supabase_enabled
from app.chat.contracts import MessageContent

logger = logging.getLogger(__name__)


# Storage-edge compatibility for old message rows that were persisted before
# NBB-011 introduced neutral runtime content parts. Keep this private to message
# storage; remove only after a database migration proves no rows still contain
# Anthropic-shaped content blocks.
def _legacy_content_blocks_to_runtime_parts(
    content_blocks: List[Any],
) -> List[Dict[str, Any]]:
    """Convert old persisted Anthropic blocks to neutral runtime content parts."""
    parts: List[Dict[str, Any]] = []
    for block in content_blocks:
        serialized = _serialize_legacy_content_block(block)
        block_type = serialized.get("type")
        if block_type == "text":
            parts.append({"type": "text", "text": str(serialized.get("text") or "")})
        elif block_type == "tool_use":
            call_id = str(serialized.get("id") or "")
            parts.append(
                {
                    "type": "tool_call",
                    "call_id": call_id,
                    "provider_call_id": call_id,
                    "name": str(serialized.get("name") or ""),
                    "arguments": dict(serialized.get("input") or {}),
                }
            )
        elif block_type == "tool_result":
            parts.append(
                {
                    "type": "tool_result",
                    "call_id": str(serialized.get("tool_use_id") or ""),
                    "name": str(serialized.get("name") or ""),
                    "content": serialized.get("content"),
                    "is_error": bool(serialized.get("is_error", False)),
                }
            )
        elif block_type in {"image", "document"}:
            parts.append(_legacy_media_block_to_runtime_part(serialized))
        else:
            parts.append(
                {
                    "type": "provider_metadata",
                    "provider": "anthropic",
                    "values": serialized,
                }
            )
    return parts


def _serialize_legacy_content_block(block: Any) -> Dict[str, Any]:
    if isinstance(block, dict):
        return dict(block)
    if hasattr(block, "model_dump"):
        value = block.model_dump(mode="json")
        if isinstance(value, dict):
            return value
    if hasattr(block, "dict"):
        value = block.dict()
        if isinstance(value, dict):
            return value
    if hasattr(block, "__dict__"):
        return {
            key: _serialize_legacy_value(value)
            for key, value in vars(block).items()
            if not key.startswith("_")
        }
    return {"type": "text", "text": str(block)}


def _serialize_legacy_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialize_legacy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_legacy_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return {
            key: _serialize_legacy_value(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def _legacy_media_block_to_runtime_part(block: Dict[str, Any]) -> Dict[str, Any]:
    source = block.get("source") if isinstance(block.get("source"), dict) else {}
    values: Dict[str, Any] = {
        "type": "media",
        "kind": "image" if block.get("type") == "image" else "document",
        "media_type": str(source.get("media_type") or ""),
        "provider_metadata": {"anthropic": block},
    }
    if source.get("type") == "base64":
        values["data"] = source.get("data")
    elif source.get("type") == "url":
        values["url"] = source.get("url")
    elif source.get("type") == "file":
        values["file_id"] = source.get("file_id")
    if block.get("filename"):
        values["filename"] = block.get("filename")
    if block.get("title"):
        values["title"] = block.get("title")
    return values


class MessageStore:
    """
    Service class for message persistence using Supabase.

    Educational Note: Messages are stored in the Supabase messages table.
    This service handles the format conversion between storage and API.
    """

    def __init__(self):
        """Initialize the message service."""
        if not is_supabase_enabled():
            raise RuntimeError(
                "Supabase is not configured. Please add SUPABASE_URL and "
                "SUPABASE_ANON_KEY to your .env file."
            )
        self.supabase = get_supabase()
        self.table = "messages"
        self.chats_table = "chats"
        # Keep local storage for agent execution logs (debugging only)
        self.projects_dir = Config.PROJECTS_DIR

    def get_messages(self, project_id: str, chat_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages from a chat.

        Args:
            project_id: The project UUID (used for validation)
            chat_id: The chat UUID

        Returns:
            List of message dicts
        """
        chat_check = (
            self.supabase.table(self.chats_table)
            .select("id")
            .eq("id", chat_id)
            .eq("project_id", project_id)
            .execute()
        )
        if not chat_check.data:
            return []

        response = (
            self.supabase.table(self.table)
            .select("*")
            .eq("chat_id", chat_id)
            .order("created_at", desc=False)
            .execute()
        )
        return [self._migrate_message_row(row) for row in response.data or []]

    def _migrate_message_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy Anthropic-shaped content to runtime content parts."""
        content = row.get("content")
        normalized = self._normalize_content_for_storage(content)
        if normalized == content:
            return row

        migrated = {**row, "content": normalized}
        try:
            self.supabase.table(self.table).update({"content": normalized}).eq(
                "id", row["id"]
            ).execute()
        except Exception as exc:
            logger.warning("Failed to migrate message %s content: %s", row.get("id"), exc)
        return migrated

    def _normalize_content_for_storage(self, content: Any) -> List[Dict[str, Any]]:
        """Return the current neutral runtime content-part shape."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}]

        if isinstance(content, dict):
            if "text" in content:
                parts = [{"type": "text", "text": str(content.get("text") or "")}]
                if content.get("error"):
                    parts.append(self._error_part())
                return parts
            if content.get("type") in self._runtime_part_types():
                return [content]
            return [
                {
                    "type": "provider_metadata",
                    "provider": "noobbook",
                    "values": content,
                }
            ]

        if isinstance(content, list):
            if all(
                isinstance(part, dict) and part.get("type") in self._runtime_part_types()
                for part in content
            ):
                return content
            return _legacy_content_blocks_to_runtime_parts(content)

        return [{"type": "text", "text": str(content) if content is not None else ""}]

    def _runtime_part_types(self) -> set[str]:
        return {"text", "tool_call", "tool_result", "media", "provider_metadata"}

    def _error_part(self) -> Dict[str, Any]:
        return {
            "type": "provider_metadata",
            "provider": "noobbook",
            "values": {"error": True},
        }

    def _content_has_error(self, content: Any) -> bool:
        if isinstance(content, dict):
            return bool(content.get("error"))
        parts = self._normalize_content_for_storage(content)
        return any(
            part.get("type") == "provider_metadata"
            and part.get("provider") == "noobbook"
            and isinstance(part.get("values"), dict)
            and part["values"].get("error")
            for part in parts
        )

    def _extract_text_content(self, content: Any) -> str:
        if isinstance(content, dict) and "text" in content:
            return str(content.get("text") or "")
        if isinstance(content, str):
            return content
        parts = self._normalize_content_for_storage(content)
        text_parts = [
            str(part.get("text") or "")
            for part in parts
            if part.get("type") == "text"
        ]
        return "\n\n".join(part for part in text_parts if part.strip())

    def _provider_content(self, role: str, content: Any) -> Any:
        parts = self._normalize_content_for_storage(content)
        visible_parts = [
            part
            for part in parts
            if not (
                part.get("type") == "provider_metadata"
                and part.get("provider") == "noobbook"
            )
        ]
        if all(part.get("type") == "text" for part in visible_parts):
            return "\n\n".join(str(part.get("text") or "") for part in visible_parts)
        return visible_parts

    def add_message(
        self,
        project_id: str,
        chat_id: str,
        role: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Add a message to a chat.

        Educational Note: This handles different content types:
        - String content for simple user/assistant messages
        - List content for runtime text/tool_call/tool_result parts

        Args:
            project_id: The project UUID
            chat_id: The chat UUID
            role: Message role ('user' or 'assistant')
            content: Message content (string or list of content parts)
            metadata: Optional metadata (model, tokens, error, etc.)

        Returns:
            The created message dict, or None if chat not found
        """
        # Verify chat exists
        chat_check = (
            self.supabase.table(self.chats_table)
            .select("id")
            .eq("id", chat_id)
            .eq("project_id", project_id)
            .execute()
        )

        if not chat_check.data:
            return None

        db_content = self._normalize_content_for_storage(content)

        # Store error flag inside the JSONB content so build_api_messages
        # can filter these out and never send them to the model.
        if metadata and metadata.get("error"):
            db_content = [*db_content, self._error_part()]

        MessageContent.model_validate(db_content)

        # Create message data
        message_data = {
            "chat_id": chat_id,
            "role": role,
            "content": db_content
        }

        # Add optional metadata
        if metadata:
            if "model" in metadata:
                message_data["model"] = metadata["model"]
            if "tokens" in metadata:
                token_data = metadata["tokens"]
                message_data["tokens_input"] = token_data.get(
                    "input",
                    token_data.get("input_tokens", 0),
                )
                message_data["tokens_output"] = token_data.get(
                    "output",
                    token_data.get("output_tokens", 0),
                )
            if "citations" in metadata:
                message_data["citations"] = metadata["citations"]
            if "cost_usd" in metadata:
                message_data["cost_usd"] = metadata["cost_usd"]

        # Insert message
        response = (
            self.supabase.table(self.table)
            .insert(message_data)
            .execute()
        )

        if response.data:
            message = response.data[0]
            # Update chat's updated_at timestamp
            self.supabase.table(self.chats_table).update({
                "updated_at": datetime.now().isoformat()
            }).eq("id", chat_id).eq("project_id", project_id).execute()

            # Format message for frontend (extract text from JSONB)
            return self._format_message_for_frontend(message)

        return None

    def _format_message_for_frontend(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a message for frontend consumption.

        Educational Note: Content is stored as JSONB runtime parts in Supabase,
        while the frontend expects a plain string. This extracts text parts.

        Args:
            message: Raw message from Supabase

        Returns:
            Message with content as string
        """
        content = message.get("content")

        text_content = self._extract_text_content(content)

        raw_content = message.get("content")
        is_error = self._content_has_error(raw_content)

        return {
            "id": message.get("id"),
            "role": message.get("role"),
            "content": text_content,
            "timestamp": message.get("created_at"),
            "model": message.get("model"),
            "citations": message.get("citations", []),
            "error": is_error,
        }

    def add_user_message(
        self,
        project_id: str,
        chat_id: str,
        content: str
    ) -> Optional[Dict[str, Any]]:
        """
        Add a user message to a chat.

        Educational Note: Convenience method for the common case of
        adding a simple text message from the user.

        Args:
            project_id: The project UUID
            chat_id: The chat UUID
            content: The user's message text

        Returns:
            The created message dict
        """
        return self.add_message(project_id, chat_id, "user", content)

    def add_assistant_message(
        self,
        project_id: str,
        chat_id: str,
        content: str,
        model: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None,
        error: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Add an assistant message to a chat.

        Educational Note: Includes metadata about the model and token usage
        for tracking and debugging purposes.

        Args:
            project_id: The project UUID
            chat_id: The chat UUID
            content: The assistant's response text
            model: Model used to generate response
            tokens: Token usage dict with 'input' and 'output'
            error: Whether this is an error message

        Returns:
            The created message dict
        """
        metadata = {}
        if model:
            metadata["model"] = model
        if tokens:
            metadata["tokens"] = tokens
        if error:
            metadata["error"] = True

        return self.add_message(project_id, chat_id, "assistant", content, metadata)

    def add_tool_result_message(
        self,
        project_id: str,
        chat_id: str,
        call_id: str,
        result: Any,
        is_error: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Add a tool result message to a chat.

        Educational Note: After a provider requests a tool call, we need to
        send back the result. This is a user message with runtime tool_result
        content; provider adapters compile it to the right wire shape.

        Args:
            project_id: The project UUID
            chat_id: The chat UUID
            call_id: The runtime/provider tool call id
            result: The tool execution result
            is_error: Whether the tool execution failed

        Returns:
            The created message dict
        """
        content = [
            {
                "type": "tool_result",
                "call_id": call_id,
                "name": "",
                "content": str(result) if not isinstance(result, str) else result,
                "is_error": is_error,
            }
        ]
        return self.add_message(project_id, chat_id, "user", content)

    def build_api_messages(
        self,
        project_id: str,
        chat_id: str,
        include_pending: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """
        Build message array for the selected model call.

        Educational Note: The the selected model expects messages in a specific format.
        This method converts stored messages to the API format, optionally
        including a pending message that hasn't been saved yet.

        Args:
            project_id: The project UUID
            chat_id: The chat UUID
            include_pending: Optional message to include at the end

        Returns:
            List of message dicts ready for the selected model
        """
        messages = self.get_messages(project_id, chat_id)

        # Convert to API format, skipping error messages.
        # Error messages are internal UI feedback (e.g. "overloaded, try again").
        # Sending them to the model as assistant responses confuses it and can cause
        # follow-up requests to fail or behave strangely.
        api_messages = []
        for msg in messages:
            content = msg.get("content")

            # Skip error messages — flagged through noobbook provider metadata.
            if self._content_has_error(content):
                continue

            api_content = self._provider_content(msg["role"], content)

            api_messages.append({
                "role": msg["role"],
                "content": api_content
            })

        # Add pending message if provided
        if include_pending:
            api_messages.append({
                "role": include_pending["role"],
                "content": include_pending["content"]
            })

        # Sanitize neutral tool_call/tool_result sequences from past errors.
        api_messages = self._sanitize_tool_sequences(api_messages)

        # Safety guard: provider replay requires messages to end with a user
        # message. If sanitization left trailing assistant messages (from
        # orphaned tool calls or error messages), strip them to prevent
        # provider request failures.
        # Also delete those rows from the DB so the chat self-heals — future requests
        # won't need to re-sanitize the same corrupted tail.
        trailing_assistant_ids = []
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                trailing_assistant_ids.append(msg["id"])
            else:
                break

        while api_messages and api_messages[-1]["role"] == "assistant":
            api_messages.pop()

        if trailing_assistant_ids:
            try:
                self.supabase.table(self.table).delete().in_("id", trailing_assistant_ids).execute()
                logger.info(
                    "Self-healed chat %s: deleted %d trailing assistant messages from DB",
                    chat_id, len(trailing_assistant_ids)
                )
            except Exception as e:
                logger.warning("Failed to self-heal chat %s DB trailing messages: %s", chat_id, e)

        # Also ensure messages start with a user message
        while api_messages and api_messages[0]["role"] != "user":
            api_messages.pop(0)

        return api_messages

    def build_runtime_messages(
        self,
        project_id: str,
        chat_id: str,
        include_pending: Optional[Dict[str, Any]] = None,
    ) -> List[RunMessage]:
        """Build neutral runtime messages for the provider-neutral runner."""
        api_messages = self.build_api_messages(
            project_id,
            chat_id,
            include_pending=include_pending,
        )
        return [
            RunMessage(
                role="tool" if self._is_tool_result_content(msg["content"]) else msg["role"],
                content=self._normalize_content_for_storage(msg["content"]),
            )
            for msg in api_messages
        ]

    def _is_tool_result_content(self, content: Any) -> bool:
        return (
            isinstance(content, list)
            and bool(content)
            and all(
                isinstance(part, dict) and part.get("type") == "tool_result"
                for part in content
            )
        )

    def _sanitize_tool_sequences(self, api_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fix broken tool_call/tool_result sequences.

        Educational Note: provider replay requires every tool call to have a
        matching tool_result in the next message. If historical data or a past
        error left an orphan, this strips it so the chat can continue.

        Steps:
        1. Strip tool_call blocks that don't have matching tool_results
        2. Remove user messages that contain only orphaned tool_results
        3. Merge consecutive same-role messages (can happen after stripping)
        """
        if not api_messages:
            return api_messages

        # --- Step 1: Find which tool-call IDs have valid tool_result matches ---
        valid_tool_call_ids: set = set()
        for i, msg in enumerate(api_messages):
            if msg["role"] != "assistant" or not isinstance(msg["content"], list):
                continue
            tool_call_ids = {
                self._tool_call_id(block) for block in msg["content"]
                if isinstance(block, dict) and self._is_tool_call_block(block)
            }
            tool_call_ids.discard(None)
            if not tool_call_ids:
                continue
            # Collect tool_result IDs from subsequent user messages
            result_ids: set = set()
            for j in range(i + 1, len(api_messages)):
                next_msg = api_messages[j]
                if next_msg["role"] == "user" and isinstance(next_msg["content"], list):
                    for block in next_msg["content"]:
                        if isinstance(block, dict) and self._is_tool_result_block(block):
                            result_ids.add(self._tool_result_id(block))
                else:
                    break  # Stop at first non-tool-result message
            # Valid only if ALL tool-call IDs have matching results
            if tool_call_ids.issubset(result_ids):
                valid_tool_call_ids.update(tool_call_ids)

        # --- Step 2: Filter out orphaned tool_call and tool_result blocks ---
        filtered: List[Dict[str, Any]] = []
        for msg in api_messages:
            if msg["role"] == "assistant" and isinstance(msg["content"], list):
                has_tool_call = any(
                    isinstance(b, dict) and self._is_tool_call_block(b)
                    for b in msg["content"]
                )
                if has_tool_call:
                    # Keep only valid tool_call blocks and all non-tool_call blocks
                    cleaned = [
                        block for block in msg["content"]
                        if not (isinstance(block, dict) and self._is_tool_call_block(block))
                        or self._tool_call_id(block) in valid_tool_call_ids
                    ]
                    # Extract text if only text blocks remain
                    if cleaned and all(isinstance(b, dict) and b.get("type") == "text" for b in cleaned):
                        text = "\n".join(b.get("text", "") for b in cleaned).strip()
                        if text:
                            filtered.append({"role": "assistant", "content": text})
                    elif cleaned:
                        filtered.append({"role": "assistant", "content": cleaned})
                    # If empty after cleaning, skip the message entirely
                    continue

            if msg["role"] == "user" and isinstance(msg["content"], list):
                has_tool_result = any(
                    isinstance(b, dict) and self._is_tool_result_block(b)
                    for b in msg["content"]
                )
                if has_tool_result:
                    # Keep only tool_results with valid IDs
                    cleaned = [
                        block for block in msg["content"]
                        if not (isinstance(block, dict) and self._is_tool_result_block(block))
                        or self._tool_result_id(block) in valid_tool_call_ids
                    ]
                    if cleaned:
                        filtered.append({"role": "user", "content": cleaned})
                    # If empty, skip (orphaned tool_result message)
                    continue

            filtered.append(msg)

        # --- Step 3: Merge consecutive same-role messages ---
        merged: List[Dict[str, Any]] = []
        for msg in filtered:
            if merged and merged[-1]["role"] == msg["role"]:
                prev_content = merged[-1]["content"]
                curr_content = msg["content"]
                # Merge two text strings
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + "\n\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    # Merge two list messages (e.g. multiple tool_result blocks)
                    merged[-1]["content"] = prev_content + curr_content
                else:
                    # Mixed types — skip merging, keep as-is to avoid breaking content blocks
                    merged.append(msg)
            else:
                merged.append(msg)

        return merged

    def _is_tool_call_block(self, block: Dict[str, Any]) -> bool:
        return block.get("type") in {"tool_call", "tool_use"}

    def _is_tool_result_block(self, block: Dict[str, Any]) -> bool:
        return block.get("type") == "tool_result"

    def _tool_call_id(self, block: Dict[str, Any]) -> Optional[str]:
        value = block.get("call_id") or block.get("id")
        return str(value) if value else None

    def _tool_result_id(self, block: Dict[str, Any]) -> Optional[str]:
        value = block.get("call_id") or block.get("tool_use_id")
        return str(value) if value else None

    def build_context_from_messages(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        Build API message array from a list of messages.

        Educational Note: This is useful for subagents or other flows
        that don't use stored chat messages but need to build context.

        Args:
            messages: List of message dicts

        Returns:
            List of message dicts ready for the selected model
        """
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]

    def update_chat_metadata(
        self,
        project_id: str,
        chat_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update chat metadata (not messages).

        Educational Note: Used for updating things like title, source_references,
        sub_agents metadata without modifying messages.

        Args:
            project_id: The project UUID
            chat_id: The chat UUID
            updates: Dict of fields to update

        Returns:
            True if successful
        """
        # Filter to allowed fields
        allowed_fields = ["title"]
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not filtered_updates:
            return True

        response = (
            self.supabase.table(self.chats_table)
            .update(filtered_updates)
            .eq("id", chat_id)
            .eq("project_id", project_id)
            .execute()
        )

        return bool(response.data)

    # =========================================================================
    # Agent Execution Logs - For storing agent debug/execution data
    # (Kept as local files for debugging - not migrated to Supabase)
    # =========================================================================

    def _get_agent_dir(self, project_id: str, agent_name: str) -> Path:
        """
        Get the directory for a specific agent's execution logs.

        Educational Note: Uses base path helpers for centralized path management.
        Currently supports 'web_agent', can be extended for other agents.

        Args:
            project_id: The project UUID
            agent_name: The agent name (e.g., 'web_agent')

        Returns:
            Path to agent's execution log directory (auto-created)
        """
        if agent_name == "web_agent":
            return get_web_agent_dir(project_id)
        else:
            # Generic fallback for future agents
            agents_dir = get_agents_dir(project_id)
            agent_dir = agents_dir / agent_name
            agent_dir.mkdir(parents=True, exist_ok=True)
            return agent_dir

    def save_agent_execution(
        self,
        project_id: str,
        agent_name: str,
        execution_id: str,
        task: str,
        messages: List[Dict[str, Any]],
        result: Dict[str, Any],
        started_at: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Save an agent execution log (local file for debugging).

        Educational Note: Agent execution logs are stored locally for debugging.
        They capture the full message chain, tool calls, and results.

        Structure: data/projects/{project_id}/agents/{agent_name}/{execution_id}.json

        Args:
            project_id: The project UUID
            agent_name: The agent name (e.g., 'web_agent')
            execution_id: Unique execution ID
            task: The task description that was given to the agent
            messages: Full message chain (includes tool_call, tool_result, etc.)
            result: Final result from the agent
            started_at: Execution start timestamp (ISO format)
            metadata: Optional additional metadata (source_id, url, etc.)

        Returns:
            The execution_id if successful, None if failed
        """
        if not project_id:
            return None

        try:
            # Get agent directory using base path helpers
            agent_dir = self._get_agent_dir(project_id, agent_name)

            # Build execution log
            execution_log = {
                "execution_id": execution_id,
                "agent_name": agent_name,
                "task": task,
                "messages": messages,
                "result": result,
                "started_at": started_at,
                "completed_at": datetime.now().isoformat()
            }

            # Add optional metadata
            if metadata:
                execution_log.update(metadata)

            # Save to file
            log_file = agent_dir / f"{execution_id}.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(execution_log, f, indent=2, ensure_ascii=False)

            return execution_id

        except Exception as e:
            logger.error("Failed to save %s execution log: %s", agent_name, e)
            return None

    def get_agent_execution(
        self,
        project_id: str,
        agent_name: str,
        execution_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific agent execution log.

        Args:
            project_id: The project UUID
            agent_name: The agent name (e.g., 'web_agent')
            execution_id: The execution UUID

        Returns:
            Execution log dict or None if not found
        """
        try:
            agent_dir = self._get_agent_dir(project_id, agent_name)
            log_file = agent_dir / f"{execution_id}.json"

            if not log_file.exists():
                return None

            with open(log_file, "r", encoding="utf-8") as f:
                return json.load(f)

        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to read %s execution log: %s", agent_name, e)
            return None

    def list_agent_executions(
        self,
        project_id: str,
        agent_name: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List agent execution logs for a project.

        Educational Note: Returns basic metadata for each execution without
        loading the full message chains. Sorted by completion time (newest first).

        Args:
            project_id: The project UUID
            agent_name: The agent name (e.g., 'web_agent')
            limit: Maximum number of executions to return

        Returns:
            List of execution summaries (id, task, completed_at, success)
        """
        try:
            agent_dir = self._get_agent_dir(project_id, agent_name)

            if not agent_dir.exists():
                return []

            executions = []
            for log_file in agent_dir.glob("*.json"):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        log = json.load(f)
                        executions.append({
                            "execution_id": log.get("execution_id"),
                            "task": log.get("task", "")[:100],  # Truncate task
                            "completed_at": log.get("completed_at"),
                            "success": log.get("result", {}).get("success", False)
                        })
                except (json.JSONDecodeError, IOError):
                    continue

            # Sort by completion time (newest first)
            executions.sort(key=lambda x: x.get("completed_at", ""), reverse=True)

            return executions[:limit]

        except Exception as e:
            logger.error("Failed to list %s executions: %s", agent_name, e)
            return []


# Singleton instance for easy import
message_service = MessageStore()
