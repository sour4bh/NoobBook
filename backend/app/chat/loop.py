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

from app.auth.identity import RequestIdentity, get_request_identity
from app.chat.context import build_system_prompt
from app.chat.message.store import message_service
from app.chat.persistence import emit_event
from app.chat.naming import submit_naming_task
from app.chat.schemas import ChatEvent, ChatResponse
from app.chat.store import chat_service
from app.chat.streaming import iter_chat_events
from app.chat.tool.policy import chat_tool_policy
from app.chat.tools.binding import bind_chat_tools
from app.config.prompt import get_project_custom_prompt, render_prompt
from app.config.context import context_loader
from app.agents.runtime import (
    ProviderRunError,
    RunLimits,
    RunRequest,
    run_with_provider,
    stream_with_provider,
)
from app.projects.store import DEFAULT_USER_ID


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


def _provider_label(provider: str) -> str:
    return {"openai": "OpenAI", "anthropic": "Anthropic"}.get(provider, provider.title())


def _format_friendly_error(error: Exception | str) -> str:
    """Map known provider API error strings to user-facing messages."""
    info = getattr(error, "error_info", None)
    if info is not None:
        if info.kind == "rate_limit":
            return "Rate limit reached. Please wait a moment and try again."
        if info.kind in {"timeout", "connection"}:
            return "The provider connection failed. Please try again."
        if info.kind == "server":
            return f"{_provider_label(info.provider)} is having trouble. Please try again shortly."
        if info.kind == "authentication":
            return f"{_provider_label(info.provider)} authentication failed. Check the API key."
        if info.kind == "permission":
            return f"{_provider_label(info.provider)} rejected the request for permission reasons."

    error_str = str(error)
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
        prompt = render_prompt(
            "default",
            project_id=project_id,
            system_override=get_project_custom_prompt(project_id),
        )
        base_prompt = prompt.system_prompt
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
            project_id=project_id,
        )

        streamed_text_parts: List[str] = []

        try:
            # Step 4: Build messages and run the selected model/tool loop.
            runtime_messages = message_service.build_runtime_messages(project_id, chat_id)
            bound_tools = bind_chat_tools(
                tools,
                project_id=project_id,
                chat_id=chat_id,
                user_id=resolved_user_id,
                mcp_registry=mcp_registry,
            )
            request = RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose="chat",
                system_prompt=system_prompt,
                messages=runtime_messages,
                tools=bound_tools,
                limits=RunLimits(
                    max_tool_turns=self.MAX_TOOL_ITERATIONS,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
                user_id=resolved_user_id,
                chat_id=chat_id,
                metadata={"tags": ["chat"], "mcp_registry": mcp_registry},
            )
            emit_event(on_event, "ping")

            if stream_text:
                def emit_delta(delta: str) -> None:
                    streamed_text_parts.append(delta)
                    if on_text_delta is not None:
                        on_text_delta(delta)

                turn_result = stream_with_provider(request, on_text_delta=emit_delta)
            else:
                turn_result = run_with_provider(request)

            # Step 5: Persist the runtime-generated tool transcript. The shared
            # runtime owns execution and pairing; chat owns durable history.
            for generated_message in turn_result.generated_messages:
                stored_role = "user" if generated_message.role == "tool" else generated_message.role
                message_service.add_message(
                    project_id=project_id,
                    chat_id=chat_id,
                    role=stored_role,
                    content=[
                        part.model_dump(mode="json")
                        for part in generated_message.content
                    ],
                )

            # Step 6: Store final text response.
            # Providers may send text before requesting tools; after tool
            # execution they may respond with more text or an empty final turn.
            # All text parts combine into the complete response shown to the user.
            final_text = turn_result.text

            assistant_msg = message_service.add_assistant_message(
                project_id=project_id,
                chat_id=chat_id,
                content=final_text if final_text.strip() else "I've processed your request.",
                model=turn_result.model,
                tokens=turn_result.usage.model_dump(mode="json"),
            )
            emit_event(on_event, "assistant_done", assistant_msg)

        except Exception as api_error:
            failed_result = (
                api_error.result
                if isinstance(api_error, ProviderRunError) and api_error.result is not None
                else None
            )
            if failed_result is not None:
                for generated_message in failed_result.generated_messages:
                    stored_role = (
                        "user"
                        if generated_message.role == "tool"
                        else generated_message.role
                    )
                    message_service.add_message(
                        project_id=project_id,
                        chat_id=chat_id,
                        role=stored_role,
                        content=[
                            part.model_dump(mode="json")
                            for part in generated_message.content
                        ],
            )

            partial_text = str(getattr(api_error, "partial_text", "") or "")
            if not partial_text.strip() and streamed_text_parts:
                partial_text = "".join(streamed_text_parts)
            error_prefix = partial_text.strip()

            friendly_error = _format_friendly_error(api_error)
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

        # Step 7: Auto-rename chat on first message (background task).
        # `chat` was read at the top, so `message_count` here is the pre-write
        # count. Naming runs in background so it doesn't block the response.
        submit_naming_task(chat, project_id, chat_id, user_message_text)

        return {
            "user_message": user_msg,
            "assistant_message": assistant_msg,
        }

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
