"""Anthropic Messages adapter for the typed agent runtime.

The rest of the app should not parse Claude content blocks directly after its
NBB-011 migration slice lands. This adapter is the boundary that compiles
runtime tool specs to Anthropic schemas, translates neutral messages to Claude
message content, and normalizes Claude responses back into runtime contracts.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from queue import Queue
from threading import Thread
from typing import Any, Optional

from app.agents.runtime.contract import (
    MediaPart,
    ProviderErrorInfo,
    ProviderErrorKind,
    ProviderMetadataPart,
    ProviderState,
    RunEvent,
    RunMessage,
    RunRequest,
    RunResult,
    StructuredResult,
    TextPart,
    ToolCall,
    ToolCallPart,
    ToolResultPart,
    Usage,
    final_event_data,
)
from app.agents.runtime.tool import (
    LocalToolSpec,
    McpProxyToolSpec,
    ProviderToolSpec,
    ToolSpec,
)
from app.providers.anthropic import content as _content
from app.providers.anthropic import response_parser as _response_parser
from app.providers.anthropic.schema import tool_schema as anthropic_tool_schema

_STREAM_DONE = object()
_RETRYABLE_ERROR_KINDS = {"connection", "timeout", "rate_limit", "server"}


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _isinstance_named(value: Any, module: Any, name: str) -> bool:
    cls = getattr(module, name, None)
    return isinstance(value, cls) if cls is not None else False


def _error_payload_fields(value: Any) -> tuple[str | None, str | None]:
    body = getattr(value, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return _field(error, "type"), _field(error, "code")
        return _field(body, "type"), _field(body, "code")
    return _field(value, "type"), _field(value, "code")


def _kind_from_status_code(status_code: int | None) -> ProviderErrorKind | None:
    if status_code is None:
        return None
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "authentication"
    if status_code == 403:
        return "permission"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422:
        return "unprocessable"
    if status_code == 429:
        return "rate_limit"
    if status_code >= 500:
        return "server"
    return None


def _status_code(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _kind_from_error_text(value: str) -> ProviderErrorKind:
    lowered = value.lower()
    if "rate" in lowered or "quota" in lowered or "429" in lowered:
        return "rate_limit"
    if "authentication" in lowered or "api key" in lowered or "401" in lowered:
        return "authentication"
    if "permission" in lowered or "forbidden" in lowered or "403" in lowered:
        return "permission"
    if "timeout" in lowered:
        return "timeout"
    if "connection" in lowered or "network" in lowered:
        return "connection"
    if "overloaded" in lowered or "server" in lowered or "5xx" in lowered:
        return "server"
    return "unknown"


def _anthropic_error_info(exc: Exception, *, model: str) -> ProviderErrorInfo:
    import anthropic

    status_code = _status_code(getattr(exc, "status_code", None))
    request_id = getattr(exc, "request_id", None)
    provider_error_type, provider_error_code = _error_payload_fields(exc)

    if _isinstance_named(exc, anthropic, "RateLimitError"):
        kind: ProviderErrorKind = "rate_limit"
    elif _isinstance_named(exc, anthropic, "APITimeoutError"):
        kind = "timeout"
    elif _isinstance_named(exc, anthropic, "APIConnectionError"):
        kind = "connection"
    elif _isinstance_named(exc, anthropic, "AuthenticationError"):
        kind = "authentication"
    elif _isinstance_named(exc, anthropic, "PermissionDeniedError"):
        kind = "permission"
    elif _isinstance_named(exc, anthropic, "BadRequestError"):
        kind = "bad_request"
    elif _isinstance_named(exc, anthropic, "NotFoundError"):
        kind = "not_found"
    elif _isinstance_named(exc, anthropic, "ConflictError"):
        kind = "conflict"
    elif _isinstance_named(exc, anthropic, "UnprocessableEntityError"):
        kind = "unprocessable"
    elif _isinstance_named(exc, anthropic, "InternalServerError"):
        kind = "server"
    else:
        kind = _kind_from_status_code(status_code) or _kind_from_error_text(str(exc))

    return ProviderErrorInfo(
        provider="anthropic",
        model=model,
        kind=kind,
        message=str(exc),
        status_code=status_code,
        provider_error_type=str(provider_error_type) if provider_error_type else None,
        provider_error_code=str(provider_error_code) if provider_error_code else None,
        request_id=str(request_id) if request_id else None,
        retryable=kind in _RETRYABLE_ERROR_KINDS,
        raw=str(exc),
    )


def _provider_error_result(info: ProviderErrorInfo) -> RunResult:
    error_data = {
        "message": info.message,
        "error_info": info.model_dump(mode="json"),
    }
    final_data = {
        "text": "",
        "status": "error",
        "error": info.message,
        "error_info": info.model_dump(mode="json"),
    }
    return RunResult(
        provider=info.provider,
        model=info.model,
        status="error",
        error=info.message,
        error_info=info,
        provider_request_ids=[info.request_id] if info.request_id else [],
        events=[
            RunEvent(type="error", data=error_data),
            RunEvent(type="final", data=final_data),
        ],
    )


class AnthropicMessagesAdapter:
    """Provider adapter around the existing Claude service."""

    name = "anthropic"

    def __init__(self, service: Optional[Any] = None) -> None:
        self._service = service

    def _claude_service(self) -> Any:
        if self._service is None:
            from app.providers.anthropic.messages import claude_service

            self._service = claude_service
        return self._service

    def compile_tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        """Compile runtime tools to Anthropic's request schema."""
        compiled: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, ProviderToolSpec):
                if not tool.provider_type:
                    raise ValueError(f"Provider tool {tool.name!r} is missing provider_type")
                provider_tool: dict[str, Any] = {
                    "type": tool.provider_type,
                    "name": tool.name,
                }
                max_uses = tool.metadata.get("max_uses")
                if max_uses is not None:
                    provider_tool["max_uses"] = max_uses
                compiled.append(provider_tool)
            elif isinstance(tool, (LocalToolSpec, McpProxyToolSpec)):
                compiled.append(anthropic_tool_schema(tool))
            else:
                raise ValueError(f"Unsupported Anthropic tool kind: {tool.kind}")
        return compiled

    def run_turn(self, request: RunRequest) -> RunResult:
        """Run one Anthropic Messages turn and normalize the response."""
        self._preflight_request(request)
        if request.output_model is not None and request.tools:
            raise ValueError(
                "Anthropic structured output mode is only supported for no-tool runs; "
                "use a typed terminating tool for agent loops"
            )
        tools = self.compile_tools(request.tools) if request.tools else None
        try:
            response = self._claude_service().send_message(
                messages=self._anthropic_messages(request),
                system_prompt=self._system_prompt(request),
                model=request.model,
                max_tokens=request.limits.max_output_tokens,
                temperature=request.limits.temperature,
                tools=tools,
                tool_choice=self._tool_choice(request),
                extra_headers=self._metadata_dict(request, "extra_headers", "anthropic_extra_headers"),
                project_id=request.project_id,
                user_id=request.user_id,
                chat_id=request.chat_id,
                tags=self._tags(request),
            )
        except Exception as exc:
            return _provider_error_result(_anthropic_error_info(exc, model=request.model))
        return self.normalize_response(
            response,
            model_fallback=request.model,
            output_model=request.output_model,
        )

    def stream_turn(self, request: RunRequest) -> Iterator[RunEvent]:
        """Stream one Anthropic turn as normalized runtime events."""
        self._preflight_request(request)
        if request.output_model is not None and request.tools:
            raise ValueError(
                "Anthropic structured output mode is only supported for no-tool runs; "
                "use a typed terminating tool for agent loops"
            )
        tools = self.compile_tools(request.tools) if request.tools else None
        events: Queue[RunEvent | RunResult | Exception | object] = Queue()

        def on_text_delta(delta: str) -> None:
            events.put(RunEvent(type="text_delta", data={"delta": delta}))

        def run_stream() -> None:
            try:
                response = self._claude_service().stream_message(
                    messages=self._anthropic_messages(request),
                    system_prompt=self._system_prompt(request),
                    model=request.model,
                    max_tokens=request.limits.max_output_tokens,
                    temperature=request.limits.temperature,
                    tools=tools,
                    tool_choice=self._tool_choice(request),
                    extra_headers=self._metadata_dict(request, "extra_headers", "anthropic_extra_headers"),
                    project_id=request.project_id,
                    on_text_delta=on_text_delta,
                    user_id=request.user_id,
                    chat_id=request.chat_id,
                    tags=self._tags(request),
                )
                events.put(
                    self.normalize_response(
                        response,
                        model_fallback=request.model,
                        output_model=request.output_model,
                    )
                )
            except Exception as exc:
                events.put(_provider_error_result(_anthropic_error_info(exc, model=request.model)))
            finally:
                events.put(_STREAM_DONE)

        thread = Thread(target=run_stream, daemon=True)
        thread.start()

        while True:
            item = events.get()
            if item is _STREAM_DONE:
                thread.join()
                return
            if isinstance(item, Exception):
                thread.join()
                raise item
            if isinstance(item, RunEvent):
                yield item
                continue
            if isinstance(item, RunResult):
                for event in item.events:
                    if event.type == "final":
                        yield RunEvent(
                            type="final",
                            data=final_event_data(item, event.data),
                        )
                        continue
                    yield event

    def count_tokens(self, text: str, *, model: Optional[str] = None) -> int:
        """Count text tokens through Anthropic's count-tokens API."""
        return self._claude_service().count_tokens(
            [{"role": "user", "content": text}],
            model=model or "claude-sonnet-4-6",
        )

    def normalize_response(
        self,
        response: dict[str, Any],
        *,
        model_fallback: str,
        output_model: Optional[type[Any]] = None,
    ) -> RunResult:
        """Normalize a raw Claude service response into runtime contracts."""
        tool_calls = [
            ToolCall(
                call_id=str(block.get("id") or ""),
                provider_call_id=str(block.get("id") or ""),
                name=str(block.get("name") or ""),
                arguments=dict(block.get("input") or {}),
            )
            for block in _response_parser.extract_tool_use_blocks(response)
        ]
        text = _response_parser.extract_text(response)
        structured = self._structured_result(
            text=text,
            output_model=output_model,
            raw=response,
        )
        content = self._content_parts(response)
        usage = response.get("usage") or {}
        stop_reason = str(response.get("stop_reason") or "")
        status = "requires_tools" if stop_reason == "tool_use" and tool_calls else "complete"
        events = [
            RunEvent(
                type="tool_call",
                data={"call_id": call.call_id, "name": call.name},
            )
            for call in tool_calls
        ]
        events.append(RunEvent(type="usage", data=dict(usage)))
        events.append(
            RunEvent(
                type="final",
                data={"text": text, "stop_reason": stop_reason, "status": status},
            )
        )

        return RunResult(
            provider=self.name,
            model=str(response.get("model") or model_fallback),
            status=status,
            text=text,
            content=content,
            tool_calls=tool_calls,
            structured=structured,
            usage=Usage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ),
            provider_state=ProviderState(
                provider=self.name,
                values={"stop_reason": stop_reason},
            ),
            events=events,
        )

    def _structured_result(
        self,
        *,
        text: str,
        output_model: Optional[type[Any]],
        raw: dict[str, Any],
    ) -> Optional[StructuredResult]:
        if output_model is None:
            return None
        try:
            parsed_json = json.loads(text or "{}")
            parsed = output_model.model_validate(parsed_json)
        except Exception as exc:
            return StructuredResult(status="invalid", error=str(exc), raw=raw)
        return StructuredResult(
            status="parsed",
            parsed=parsed.model_dump(mode="json"),
            raw=raw,
        )

    def _content_parts(self, response: dict[str, Any]) -> list[Any]:
        return self._content_parts_from_blocks(response.get("content_blocks", []))

    def _content_parts_from_blocks(self, content_blocks: list[Any]) -> list[Any]:
        parts: list[Any] = []
        for block in _content.serialize_content_blocks(content_blocks):
            block_type = block.get("type")
            if block_type == "text":
                parts.append(TextPart(text=str(block.get("text") or "")))
            elif block_type == "tool_use":
                call_id = str(block.get("id") or "")
                parts.append(
                    ToolCallPart(
                        call_id=call_id,
                        provider_call_id=call_id,
                        name=str(block.get("name") or ""),
                        arguments=dict(block.get("input") or {}),
                    )
                )
            elif block_type == "tool_result":
                parts.append(
                    ToolResultPart(
                        call_id=str(block.get("tool_use_id") or ""),
                        name=str(block.get("name") or ""),
                        content=block.get("content"),
                        is_error=bool(block.get("is_error", False)),
                    )
                )
            else:
                parts.append(ProviderMetadataPart(provider=self.name, values=block))
        return parts

    def _anthropic_messages(self, request: RunRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                messages.append(
                    {
                        "role": "user",
                        "content": self._tool_result_blocks(message),
                    }
                )
                continue
            messages.append(
                {
                    "role": message.role,
                    "content": self._message_content(message),
                }
            )
        return messages

    def _message_content(self, message: RunMessage) -> str | list[dict[str, Any]]:
        if len(message.content) == 1 and isinstance(message.content[0], TextPart):
            return message.content[0].text

        blocks: list[dict[str, Any]] = []
        for part in message.content:
            if isinstance(part, TextPart):
                blocks.append({"type": "text", "text": part.text})
            elif isinstance(part, ToolCallPart):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": part.provider_call_id or part.call_id,
                        "name": part.name,
                        "input": part.arguments,
                    }
                )
            elif isinstance(part, ToolResultPart):
                blocks.extend(self._tool_result_blocks(message))
                break
            elif isinstance(part, MediaPart):
                blocks.append(self._media_block(part))
            elif (
                isinstance(part, ProviderMetadataPart)
                and part.provider == self.name
                and "type" in part.values
            ):
                blocks.append(dict(part.values))
        return blocks

    def _media_block(self, part: MediaPart) -> dict[str, Any]:
        if part.data:
            source = {
                "type": "base64",
                "media_type": part.media_type,
                "data": part.data,
            }
        elif part.url:
            source = {"type": "url", "url": part.url}
        elif part.file_id:
            source = {"type": "file", "file_id": part.file_id}
        else:
            raise ValueError(f"Media part {part.kind!r} has no data, url, or file_id")

        block: dict[str, Any] = {"type": part.kind, "source": source}
        if part.filename:
            block["filename"] = part.filename
        if part.title:
            block["title"] = part.title
        self._copy_provider_media_metadata(block, part)
        return block

    def _copy_provider_media_metadata(
        self,
        block: dict[str, Any],
        part: MediaPart,
    ) -> None:
        metadata = part.provider_metadata.get(self.name)
        if not isinstance(metadata, dict):
            return
        for key, value in metadata.items():
            if key in {"type", "source"} or key in block:
                continue
            block[key] = value

    def _tool_result_blocks(self, message: RunMessage) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for part in message.content:
            if not isinstance(part, ToolResultPart):
                continue
            result = {
                "tool_use_id": part.call_id,
                "result": part.content if isinstance(part.content, str) else str(part.content),
                "is_error": part.is_error,
            }
            results.append(result)
        return _content.build_tool_result_content(results)

    def _system_prompt(self, request: RunRequest) -> Optional[str]:
        system_parts: list[str] = []
        if request.system_prompt:
            system_parts.append(request.system_prompt)
        for message in request.messages:
            if message.role != "system":
                continue
            for part in message.content:
                if isinstance(part, TextPart):
                    system_parts.append(part.text)
        if request.output_model is not None and not request.tools:
            schema = request.output_model.model_json_schema(by_alias=True)
            system_parts.append(
                "Return only a JSON object that validates against this schema. "
                "Do not include markdown fences or explanatory text.\n"
                + json.dumps(schema, ensure_ascii=False)
            )
        return "\n\n".join(system_parts) or None

    def _metadata_dict(
        self,
        request: RunRequest,
        *keys: str,
    ) -> Optional[dict[str, Any]]:
        for key in keys:
            value = request.metadata.get(key)
            if isinstance(value, dict):
                return value
        return None

    def _tool_choice(self, request: RunRequest) -> Optional[dict[str, Any]]:
        if request.tool_choice is not None:
            if request.tool_choice.type == "auto":
                return {"type": "auto"}
            if request.tool_choice.type == "any":
                return {"type": "any"}
            if request.tool_choice.type == "none":
                return {"type": "none"}
            if request.tool_choice.type == "tool":
                return {"type": "tool", "name": request.tool_choice.name}
        return self._metadata_dict(request, "tool_choice", "anthropic_tool_choice")

    def _preflight_request(self, request: RunRequest) -> None:
        if request.tool_choice is None:
            return
        if request.tool_choice.type in {"any", "tool"} and not request.tools:
            raise ValueError(
                f"Anthropic tool_choice={request.tool_choice.type!r} requires tools"
            )
        if request.tool_choice.type != "tool":
            return
        tool_names = {tool.name for tool in request.tools}
        if request.tool_choice.name not in tool_names:
            raise ValueError(
                f"Anthropic tool_choice requested unavailable tool "
                f"{request.tool_choice.name!r}"
            )

    def _tags(self, request: RunRequest) -> list[str]:
        tags = request.metadata.get("tags")
        if isinstance(tags, list) and all(isinstance(item, str) for item in tags):
            return tags
        return [request.purpose]


anthropic_adapter = AnthropicMessagesAdapter()
