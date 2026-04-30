"""Shared provider-neutral local-tool loop."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, Optional, cast

from pydantic import BaseModel, ValidationError

from app.agents.runtime.contract import (
    ContentPart,
    ProviderAdapter,
    RunEvent,
    RunMessage,
    RunRequest,
    RunResult,
    ToolCall,
    ToolCallPart,
    ToolResult,
    ToolResultPart,
    Usage,
    result_from_final_event,
)
from app.agents.runtime.cost import check_user_spending_limit, record_result_usage
from app.agents.runtime.error import ProviderRunError, ToolIterationLimitError
from app.agents.runtime.tool import (
    LocalToolSpec,
    McpProxyToolSpec,
    ToolContext,
    ToolOutput,
    ToolSpec,
)


class RuntimeRunner:
    """Execute a model/tool loop using provider adapters and typed tools."""

    def run(self, request: RunRequest, adapter: ProviderAdapter) -> RunResult:
        """Run until the provider returns a final result or the limit is hit."""
        return self._run_loop(request, adapter, stream=False)

    def stream(
        self,
        request: RunRequest,
        adapter: ProviderAdapter,
        *,
        on_event: Optional[Callable[[RunEvent], None]] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> RunResult:
        """Stream provider turns while preserving the same contract as ``run``."""
        return self._run_loop(
            request,
            adapter,
            stream=True,
            on_event=on_event,
            on_text_delta=on_text_delta,
        )

    def _run_loop(
        self,
        request: RunRequest,
        adapter: ProviderAdapter,
        *,
        stream: bool,
        on_event: Optional[Callable[[RunEvent], None]] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> RunResult:
        current_request  = request
        tool_results: list[ToolResult] = []
        events: list[RunEvent] = []
        usage = Usage()
        provider_request_ids: list[str] = []
        generated_messages: list[RunMessage] = []
        text_parts: list[str] = []

        # main agent loop
        for turn_index in range(request.limits.max_tool_turns + 1):
            limit_error = check_user_spending_limit(request.user_id)
            if limit_error:
                raise RuntimeError(limit_error)

            if stream:
                result = _result_from_stream_events(
                    provider=str(current_request.provider),
                    model=current_request.model,
                    events=adapter.stream_turn(current_request),
                    on_event=on_event,
                    on_text_delta=on_text_delta,
                )
            else:
                result = adapter.run_turn(current_request)

            record_result_usage(
                project_id=current_request.project_id,
                provider=result.provider,
                model=result.model,
                usage=result.usage,
                user_id=current_request.user_id,
                chat_id=current_request.chat_id,
            )
            events.extend(result.events)
            usage = _merge_usage(usage, result.usage)
            provider_request_ids.extend(result.provider_request_ids)
            if result.text.strip():
                text_parts.append(result.text)

            if result.status == "error":
                failed_result = result.model_copy(
                    update={
                        "tool_results": [*tool_results, *result.tool_results],
                        "usage": usage,
                        "provider_request_ids": provider_request_ids,
                        "events": events,
                        "generated_messages": [
                            *generated_messages,
                            *result.generated_messages,
                        ],
                        "text": "\n\n".join(text_parts) or result.text,
                    }
                )
                raise ProviderRunError.from_result(failed_result)

            if result.status != "requires_tools" or not result.tool_calls:
                return result.model_copy(
                    update={
                        "tool_results": [*tool_results, *result.tool_results],
                        "usage": usage,
                        "provider_request_ids": provider_request_ids,
                        "events": events,
                        "generated_messages": [
                            *generated_messages,
                            *result.generated_messages,
                        ],
                        "text": "\n\n".join(text_parts) or result.text,
                    }
                )

            if turn_index >= request.limits.max_tool_turns:
                raise ToolIterationLimitError(
                    f"model exceeded {request.limits.max_tool_turns} tool turns"
                )

            # Tool call executions
            executions = self._execute_tool_calls(current_request, result.tool_calls)
            turn_results = [execution.result for execution in executions]
            tool_results.extend(turn_results)
            for item in turn_results:
                event = RunEvent(
                    type="tool_result",
                    data={
                        "call_id": item.call_id,
                        "name": item.name,
                        "is_error": item.is_error,
                    },
                )
                events.append(event)
                if on_event is not None:
                    on_event(event)

            # RunMessage from RunResult
            assistant_message, tool_message = self._tool_turn_messages(
                result,
                turn_results,
            )
            generated_messages.extend([assistant_message, tool_message])

            terminating_names = _successful_terminating_tool_names(executions)
            if terminating_names:
                final_event = RunEvent(
                    type="final",
                    data={
                        "text": result.text,
                        "status": "complete",
                        "terminated_by_tools": terminating_names,
                    },
                )
                events.append(final_event)
                if on_event is not None:
                    on_event(final_event)
                return result.model_copy(
                    update={
                        "status": "complete",
                        "tool_results": [*tool_results, *result.tool_results],
                        "usage": usage,
                        "provider_request_ids": provider_request_ids,
                        "events": events,
                        "generated_messages": generated_messages,
                        "terminated_by_tools": terminating_names,
                        "text": "\n\n".join(text_parts) or result.text,
                    }
                )

            current_request = self._with_tool_results(
                current_request,
                result,
                assistant_message,
                tool_message,
            )

        raise ToolIterationLimitError(
            f"model exceeded {request.limits.max_tool_turns} tool turns"
        )

    def _execute_tool_calls(
        self,
        request: RunRequest,
        tool_calls: list[Any],
    ) -> list["_ToolExecution"]:
        tool_map = {tool.name: tool for tool in request.tools}
        context = ToolContext(
            project_id=request.project_id,
            user_id=request.user_id,
            workspace_id=request.workspace_id,
            chat_id=request.chat_id,
            metadata=request.metadata,
        )

        results: list[_ToolExecution] = []
        for call in tool_calls:
            tool = tool_map.get(call.name)
            if tool is None:
                results.append(
                    _ToolExecution(
                        tool=None,
                        parsed_input=None,
                        result=ToolResult(
                            call_id=call.call_id,
                            name=call.name,
                            content=f"Unknown tool: {call.name}",
                            is_error=True,
                        ),
                    )
                )
                continue
            results.append(self._execute_one(tool, call, context))
        return results

    def _execute_one(
        self,
        tool: ToolSpec,
        call: Any,
        context: ToolContext,
    ) -> "_ToolExecution":
        try:
            if not isinstance(tool, (LocalToolSpec, McpProxyToolSpec)):
                raise ValueError(f"Tool {tool.name!r} is not locally executable")
            parsed_input = tool.validate_input(call.arguments)
            content = tool.execute_validated(parsed_input, context)
            is_error = False
            if isinstance(content, ToolOutput):
                is_error = content.is_error
                content = content.content
            return _ToolExecution(
                tool=tool,
                parsed_input=parsed_input,
                result=ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    content=content,
                    is_error=is_error,
                ),
            )
        except ValidationError as exc:
            return _ToolExecution(
                tool=tool if isinstance(tool, (LocalToolSpec, McpProxyToolSpec)) else None,
                parsed_input=None,
                result=ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    content=f"Invalid tool input: {exc}",
                    is_error=True,
                ),
            )
        except Exception as exc:
            return _ToolExecution(
                tool=tool if isinstance(tool, (LocalToolSpec, McpProxyToolSpec)) else None,
                parsed_input=None,
                result=ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    content=f"Tool execution failed: {exc}",
                    is_error=True,
                ),
            )

    def _tool_turn_messages(
        self,
        result: RunResult,
        tool_results: list[ToolResult],
    ) -> tuple[RunMessage, RunMessage]:
        assistant_content: list[ContentPart] = list(result.content)
        if not assistant_content:
            assistant_content = [
                ToolCallPart(
                    call_id=call.call_id,
                    name=call.name,
                    arguments=call.arguments,
                    provider_call_id=call.provider_call_id,
                )
                for call in result.tool_calls
            ]
        assistant_message = RunMessage(role="assistant", content=assistant_content)
        tool_message = RunMessage(
            role="tool",
            content=[
                ToolResultPart(
                    call_id=item.call_id,
                    name=item.name,
                    content=item.content,
                    is_error=item.is_error,
                )
                for item in tool_results
            ],
        )
        return assistant_message, tool_message

    def _with_tool_results(
        self,
        request: RunRequest,
        result: RunResult,
        assistant_message: RunMessage,
        tool_message: RunMessage,
    ) -> RunRequest:
        return request.model_copy(
            update={
                "messages": [*request.messages, assistant_message, tool_message],
                "provider_state": result.provider_state,
            }
        )


@dataclass
class _ToolExecution:
    tool: LocalToolSpec | McpProxyToolSpec | None
    parsed_input: BaseModel | None
    result: ToolResult


def _result_from_stream_events(
    *,
    provider: str,
    model: str,
    events: Iterable[RunEvent],
    on_event: Optional[Callable[[RunEvent], None]],
    on_text_delta: Optional[Callable[[str], None]],
) -> RunResult:
    collected_events: list[RunEvent] = []
    text_parts: list[str] = []
    tool_calls: dict[str, ToolCall] = {}
    usage = Usage()
    final_text = ""
    final_status: Optional[Literal["complete", "requires_tools", "error"]] = None
    final_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    for event in events:
        collected_events.append(event)
        if on_event is not None:
            on_event(event)
        if event.type == "text_delta":
            delta = str(event.data.get("delta") or "")
            if delta:
                text_parts.append(delta)
                if on_text_delta:
                    on_text_delta(delta)
            continue

        if event.type == "tool_call":
            call_id = str(event.data.get("call_id") or "")
            if not call_id:
                continue
            raw_arguments = event.data.get("arguments", {})
            if isinstance(raw_arguments, str):
                try:
                    raw_arguments = json.loads(raw_arguments or "{}")
                except json.JSONDecodeError:
                    raw_arguments = {}
            arguments = (
                cast(dict[str, Any], raw_arguments)
                if isinstance(raw_arguments, dict)
                else {}
            )
            tool_calls[call_id] = ToolCall(
                call_id=call_id,
                provider_call_id=call_id,
                name=str(event.data.get("name") or ""),
                arguments=arguments,
            )
            continue

        if event.type == "usage":
            usage = Usage.model_validate(event.data)
            continue

        if event.type == "final":
            final_data = dict(event.data)
            final_text = str(event.data.get("text") or "")
            status_value = event.data.get("status")
            if status_value in {"complete", "requires_tools", "error"}:
                final_status = cast(
                    Literal["complete", "requires_tools", "error"],
                    status_value,
                )
            continue

        if event.type == "error":
            # Progress events are not authoritative final state. Keep this as a
            # fallback error message for providers that emit an error event
            # without a complete final result payload.
            error = str(event.data.get("message") or event.data or "Provider stream failed")

    if final_data is not None:
        authoritative = result_from_final_event(
            provider=provider,
            model=model,
            data=final_data,
            events=collected_events,
            error=error,
            streamed_text="".join(text_parts),
        )
        if authoritative is not None:
            return authoritative

    calls = list(tool_calls.values())
    text = final_text or "".join(text_parts)
    status = final_status or ("requires_tools" if calls else "complete")
    if error:
        status = "error"

    return RunResult(
        provider=provider,
        model=model,
        status=status,
        text=text,
        content=[
            ToolCallPart(
                call_id=call.call_id,
                provider_call_id=call.provider_call_id,
                name=call.name,
                arguments=call.arguments,
            )
            for call in calls
        ],
        tool_calls=calls,
        usage=usage,
        events=collected_events,
        error=error,
    )


def _merge_usage(left: Usage, right: Usage) -> Usage:
    """Return whole-run usage by summing every provider turn."""
    provider_units = dict(left.provider_units)
    for key, value in right.provider_units.items():
        provider_units[key] = provider_units.get(key, 0) + value
    return Usage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cache_creation_input_tokens=(
            left.cache_creation_input_tokens + right.cache_creation_input_tokens
        ),
        cache_read_input_tokens=left.cache_read_input_tokens + right.cache_read_input_tokens,
        provider_units=provider_units,
    )


def _successful_terminating_tool_names(executions: list[_ToolExecution]) -> list[str]:
    names: list[str] = []
    for execution in executions:
        if execution.result.is_error or execution.tool is None:
            continue
        if execution.tool.terminates_run:
            names.append(execution.result.name)
            continue
        flag_name = execution.tool.terminates_when
        if flag_name and execution.parsed_input is not None:
            if bool(getattr(execution.parsed_input, flag_name, False)):
                names.append(execution.result.name)
    return sorted(set(names))
