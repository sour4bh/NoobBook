"""
Shared chat agentic loop: tool dispatch, tool-use/tool-result pairing,
and the user/assistant write order required by NBB-205 Contract 1.

Class form is mandated by NBB-302: the loop owns real state (lazy
tool definitions are held by `chat.tool.policy.ChatToolPolicy`, the
iteration cap lives here as `MAX_TOOL_ITERATIONS`). Module-level
`run_send` and `run_stream` exist as the public surface entry points
that `app.chat.send` / `app.chat.stream` delegate to.
"""
import logging
from typing import Any, Callable, Dict, Iterator, List, Optional

from flask import has_request_context

from app.auth.identity import RequestIdentity
from app.background.tasks import task_service
from app.chat import memory as chat_memory
from app.chat.context import build_system_prompt
from app.chat.message.store import message_service
from app.chat.persistence import emit_event
from app.chat.naming import submit_naming_task
from app.chat.schemas import ChatEvent, ChatResponse
from app.chat.store import chat_service
from app.chat.stream import ClaudeStreamError, call_claude, iter_chat_events
from app.chat.tool.policy import chat_tool_policy
from app.config import context_loader, prompt_loader
from app.projects.store import DEFAULT_USER_ID
from app.providers.anthropic.content import serialize_content_blocks
from app.providers.anthropic.response_parser import (
    extract_tool_use_blocks,
    is_tool_use,
)
from app.services.auth.rbac import get_request_identity
from app.services.integrations.knowledge_bases import knowledge_base_service
from app.services.integrations.mcp.mcp_tool_service import mcp_tool_service
from app.services.tool_executors import source_search_executor, studio_signal_executor
from app.sources.analysis.csv import entry as csv_entry
from app.sources.analysis.database import entry as database_entry
from app.sources.analysis.freshdesk import entry as freshdesk_entry


logger = logging.getLogger(__name__)


def _file_ext(source: Dict[str, Any]) -> str:
    """Lower-cased file extension stored inside `embedding_info`."""
    embedding_info = source.get("embedding_info", {}) or {}
    return (embedding_info.get("file_extension") or "").lower()


def _resolve_user_id(user_id: Optional[str]) -> str:
    """Resolve the active user for chat execution."""
    if user_id:
        return user_id
    identity = get_request_identity() if has_request_context() else None
    return identity.user_id if identity else DEFAULT_USER_ID


def _format_friendly_error(error_str: str) -> str:
    """Map known Claude API error strings to user-facing messages."""
    if "overloaded_error" in error_str or "overloaded" in error_str.lower():
        return (
            "Overloaded error is on Anthropic's (Claude's) end, not NoobBook. "
            "Please try again in a moment."
        )
    if "rate_limit" in error_str:
        return "Rate limit reached. Please wait a moment and try again."
    if (
        "assistant message prefill" in error_str
        or "must end with a user message" in error_str
    ):
        return (
            "Something went wrong with the message sequence. "
            "Please try sending your message again."
        )
    return f"Sorry, I encountered an error: {error_str}"


class ChatLoop:
    """Run a chat turn end-to-end: prompt, tools, agentic loop, persistence."""

    # Maximum tool iterations to prevent infinite loops
    MAX_TOOL_ITERATIONS = 10

    def run_send(
        self,
        project_id: str,
        chat_id: str,
        message: str,
        identity: Optional[RequestIdentity],
    ) -> ChatResponse:
        """Run the non-streaming chat flow."""
        user_id = identity.user_id if identity is not None else None
        result = self._run_message_flow(
            project_id=project_id,
            chat_id=chat_id,
            user_message_text=message,
            stream_text=False,
            user_id=user_id,
        )
        return {
            "user_message": result["user_message"],
            "assistant_message": result["assistant_message"],
        }

    def run_stream(
        self,
        project_id: str,
        chat_id: str,
        message: str,
        identity: Optional[RequestIdentity],
    ) -> Iterator[ChatEvent]:
        """Run the streaming chat flow as an SSE-friendly generator."""
        user_id = identity.user_id if identity is not None else None

        def runner(emit: Callable[[str, Dict[str, Any]], None]) -> None:
            self._run_message_flow(
                project_id=project_id,
                chat_id=chat_id,
                user_message_text=message,
                stream_text=True,
                user_id=user_id,
                on_text_delta=lambda delta: emit("assistant_delta", {"delta": delta}),
                on_event=emit,
            )

        return iter_chat_events(runner)

    def _run_message_flow(
        self,
        project_id: str,
        chat_id: str,
        user_message_text: str,
        *,
        stream_text: bool = False,
        user_id: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Shared chat runner for both non-streaming and streaming flows."""
        resolved_user_id = _resolve_user_id(user_id)

        # Verify chat exists. The same row is reused at the bottom for the
        # naming gate; `message_count` here is the pre-write count.
        chat = chat_service.get_chat(project_id, chat_id)
        if not chat:
            raise ValueError("Chat not found")

        # Step 1: Store user message
        user_msg = message_service.add_user_message(project_id, chat_id, user_message_text)
        emit_event(on_event, "user_message", user_msg)

        # Step 2: Get config and build system prompt
        # Per-chat source selection:
        # None = legacy chat (never set) -> fall back to all ready sources
        # [] = explicitly no sources selected
        selected_source_ids = chat.get("selected_source_ids")
        prompt_config = prompt_loader.get_project_prompt_config(project_id)
        base_prompt = prompt_config.get("system_prompt", "")
        system_prompt = build_system_prompt(
            project_id,
            base_prompt,
            user_id=resolved_user_id,
            selected_source_ids=selected_source_ids,
        )

        # Step 3: Pick tools (memory always available, search for non-CSV, analyzer for CSV)
        active_sources = context_loader.get_active_sources(
            project_id, selected_source_ids=selected_source_ids
        )
        csv_sources = [s for s in active_sources if _file_ext(s) == ".csv"]
        database_sources = [s for s in active_sources if _file_ext(s) == ".database"]
        freshdesk_sources = [s for s in active_sources if _file_ext(s) == ".freshdesk"]
        jira_sources = [s for s in active_sources if _file_ext(s) == ".jira"]
        mixpanel_sources = [s for s in active_sources if _file_ext(s) == ".mixpanel"]
        non_csv_sources = [
            s for s in active_sources
            if _file_ext(s) not in (".csv", ".database", ".freshdesk", ".jira", ".mixpanel")
        ]
        tools, mcp_registry = chat_tool_policy.select_tools(
            has_active_sources=bool(non_csv_sources),
            has_csv_sources=bool(csv_sources),
            has_database_sources=bool(database_sources),
            has_freshdesk_sources=bool(freshdesk_sources),
            has_jira_sources=bool(jira_sources),
            has_mixpanel_sources=bool(mixpanel_sources),
            user_id=resolved_user_id,
        )

        accumulated_text_parts: List[str] = []

        try:
            # Step 4: Build messages and call Claude
            api_messages = message_service.build_api_messages(project_id, chat_id)
            emit_event(on_event, "ping")

            response, response_text = call_claude(
                stream_text=stream_text,
                on_text_delta=on_text_delta,
                messages=api_messages,
                system_prompt=system_prompt,
                model=prompt_config.get("model"),
                max_tokens=prompt_config.get("max_tokens"),
                temperature=prompt_config.get("temperature"),
                tools=tools,
                project_id=project_id,
                user_id=resolved_user_id,
                chat_id=chat_id,
                tags=["chat"],
            )
            if response_text.strip():
                accumulated_text_parts.append(response_text)

            # Step 5: Handle tool use loop
            # When Claude wants to use tools, stop_reason is "tool_use".
            # We must execute tools and send back tool_result for each tool_use block.
            # Claude can respond with text + tool_use together: the text is the response
            # to the user, the tool_use is for background processing. We accumulate
            # text from all responses so we don't lose it.
            iteration = 0

            while is_tool_use(response) and iteration < self.MAX_TOOL_ITERATIONS:
                iteration += 1

                # Get tool_use blocks from response (can be multiple for parallel tool calls)
                tool_use_blocks = extract_tool_use_blocks(response)

                if not tool_use_blocks:
                    break

                # Store the assistant's tool_use response.
                # The message chain must be:
                # user -> assistant (tool_use[]) -> user (tool_result[]) -> assistant
                # Tool_use response is stored before the tool_result.
                serialized_content = serialize_content_blocks(
                    response.get("content_blocks", [])
                )
                message_service.add_message(
                    project_id=project_id,
                    chat_id=chat_id,
                    role="assistant",
                    content=serialized_content,
                )

                # Execute each tool and add results.
                # Each tool execution is wrapped in try/except so a tool_result is
                # ALWAYS stored. Otherwise an exception orphans the tool_use block
                # (no matching tool_result), corrupting the message history and
                # causing Claude API 400 errors on every subsequent message.
                for tool_block in tool_use_blocks:
                    tool_id = tool_block.get("id")
                    tool_name = tool_block.get("name")
                    tool_input = tool_block.get("input", {})

                    try:
                        result = self._execute_tool(
                            project_id,
                            chat_id,
                            tool_name,
                            tool_input,
                            user_id=resolved_user_id,
                            mcp_registry=mcp_registry,
                        )
                        is_error = False
                    except Exception as tool_error:
                        logger.error(f"Tool execution failed for {tool_name}: {tool_error}")
                        result = f"Tool execution failed: {str(tool_error)}"
                        is_error = True

                    message_service.add_tool_result_message(
                        project_id=project_id,
                        chat_id=chat_id,
                        tool_use_id=tool_id,
                        result=result,
                        is_error=is_error,
                    )

                # Rebuild messages and call Claude again
                api_messages = message_service.build_api_messages(project_id, chat_id)
                emit_event(on_event, "ping")

                response, response_text = call_claude(
                    stream_text=stream_text,
                    on_text_delta=on_text_delta,
                    messages=api_messages,
                    system_prompt=system_prompt,
                    model=prompt_config.get("model"),
                    max_tokens=prompt_config.get("max_tokens"),
                    temperature=prompt_config.get("temperature"),
                    tools=tools,
                    project_id=project_id,
                    user_id=resolved_user_id,
                    chat_id=chat_id,
                    tags=["chat"],
                )
                if response_text.strip():
                    accumulated_text_parts.append(response_text)

            # Step 6: Store final text response.
            # When Claude sends text + tool_use, the text comes first.
            # After tool execution, Claude may respond with more text OR empty.
            # All text parts combine into the complete response shown to the user.
            final_text = "\n\n".join(accumulated_text_parts) if accumulated_text_parts else ""

            assistant_msg = message_service.add_assistant_message(
                project_id=project_id,
                chat_id=chat_id,
                content=final_text if final_text.strip() else "I've processed your request.",
                model=response.get("model"),
                tokens=response.get("usage"),
            )
            emit_event(on_event, "assistant_done", assistant_msg)

        except Exception as api_error:
            partial_text = api_error.partial_text if isinstance(api_error, ClaudeStreamError) else ""
            if partial_text.strip():
                accumulated_text_parts.append(partial_text)
            error_prefix = "\n\n".join(part for part in accumulated_text_parts if part.strip())

            friendly_error = _format_friendly_error(str(api_error))
            error_content = (
                f"{error_prefix}\n\n{friendly_error}" if error_prefix else friendly_error
            )

            assistant_msg = message_service.add_assistant_message(
                project_id=project_id,
                chat_id=chat_id,
                content=error_content,
                error=True,
            )
            emit_event(
                on_event,
                "error",
                {
                    "message": str(api_error),
                    "assistant_message": assistant_msg,
                },
            )

        # Step 7: Sync chat index
        chat_service.sync_chat_to_index(project_id, chat_id)

        # Step 8: Auto-rename chat on first message (background task).
        # `chat` was read at the top, so `message_count` here is the pre-write
        # count. Naming runs in background so it doesn't block the response.
        submit_naming_task(chat, project_id, chat_id, user_message_text)

        return {
            "user_message": user_msg,
            "assistant_message": assistant_msg,
        }

    def _execute_tool(
        self,
        project_id: str,
        chat_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        user_id: Optional[str] = None,
        mcp_registry: Optional[Dict] = None,
    ) -> str:
        """
        Route a tool call to its executor and return the result string.

        Routing here is intentionally explicit and matches NBB-302's locked
        in-scope mapping; redesigning routing is NBB-303's job.
        """
        if tool_name == "search_sources":
            result = source_search_executor.execute(
                project_id=project_id,
                source_id=tool_input.get("source_id", ""),
                keywords=tool_input.get("keywords"),
                query=tool_input.get("query"),
            )
            if result.get("success"):
                return result.get("content", "No content found")
            return f"Error: {result.get('error', 'Unknown error')}"

        if tool_name == "store_memory":
            # Memory tool returns immediately, actual update happens in background.
            result = chat_memory.store(
                project_id=project_id,
                user_memory=tool_input.get("user_memory"),
                project_memory=tool_input.get("project_memory"),
                why_generated=tool_input.get("why_generated", ""),
                user_id=user_id,
            )
            if result.get("success"):
                return result.get("message", "Memory stored successfully")
            return f"Error: {result.get('message', 'Unknown error')}"

        if tool_name == "analyze_csv_agent":
            # CSV analyzer agent for answering questions about CSV data
            result = csv_entry.execute(
                project_id=project_id,
                source_id=tool_input.get("source_id", ""),
                query=tool_input.get("query", ""),
                chat_id=chat_id,
                user_id=user_id,
            )
            if result.get("success"):
                content = result.get("content", "No analysis result")
                # Filenames are auto-generated unique IDs. Main chat Claude MUST
                # use these exact filenames with [[image:FILENAME]].
                if result.get("image_paths"):
                    content += "\n\nGenerated visualizations (use these exact filenames):\n"
                    for filename in result["image_paths"]:
                        content += f"- [[image:{filename}]]\n"
                return content
            return f"Error: {result.get('error', 'Analysis failed')}"

        if tool_name == "analyze_database_agent":
            # Database analyzer agent for answering questions using live SQL
            result = database_entry.execute(
                project_id=project_id,
                source_id=tool_input.get("source_id", ""),
                query=tool_input.get("query", ""),
                chat_id=chat_id,
                user_id=user_id,
            )
            if result.get("success"):
                return result.get("content", "No analysis result")
            return f"Error: {result.get('error', 'Analysis failed')}"

        if tool_name == "analyze_freshdesk_agent":
            # Freshdesk analyzer agent for answering questions about ticket data
            result = freshdesk_entry.execute(
                project_id=project_id,
                source_id=tool_input.get("source_id", ""),
                query=tool_input.get("query", ""),
                chat_id=chat_id,
                user_id=user_id,
            )
            if result.get("success"):
                return result.get("content", "No analysis result")
            return f"Error: {result.get('error', 'Analysis failed')}"

        if tool_name == "studio_signal":
            # Studio signal returns immediately, actual storage happens in background.
            result = studio_signal_executor.execute(
                project_id=project_id,
                chat_id=chat_id,
                signals=tool_input.get("signals", []),
            )
            if result.get("success"):
                return result.get("message", "Studio signals activated")
            return f"Error: {result.get('message', 'Unknown error')}"

        if knowledge_base_service.can_handle(tool_name):
            # Route to knowledge base service (Jira, Notion, GitHub, etc.)
            return knowledge_base_service.execute(
                project_id=project_id,
                chat_id=chat_id,
                tool_name=tool_name,
                tool_input=tool_input,
            )

        if mcp_registry and mcp_tool_service.can_handle(tool_name):
            # Route to MCP tool service (Freshdesk, GitHub MCP, etc.)
            return mcp_tool_service.execute(
                tool_name=tool_name,
                tool_input=tool_input,
                registry=mcp_registry,
            )

        return f"Unknown tool: {tool_name}"


def run_send(
    project_id: str,
    chat_id: str,
    message: str,
    identity: Optional[RequestIdentity],
) -> ChatResponse:
    """Module-level entry point used by `app.chat.send`."""
    return ChatLoop().run_send(project_id, chat_id, message, identity)


def run_stream(
    project_id: str,
    chat_id: str,
    message: str,
    identity: Optional[RequestIdentity],
) -> Iterator[ChatEvent]:
    """Module-level entry point used by `app.chat.stream`."""
    return ChatLoop().run_stream(project_id, chat_id, message, identity)
