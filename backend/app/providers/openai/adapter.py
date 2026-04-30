"""OpenAI Responses adapter for the typed agent runtime."""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import import_module
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
from app.providers.openai.schema import function_schema, response_format


_ERROR_RESPONSE_STATUSES = {"cancelled", "failed", "incomplete"}
_TERMINAL_RESPONSE_EVENTS = {
    "response.completed",
    "response.cancelled",
    "response.done",
    "response.failed",
    "response.incomplete",
}

_RETRYABLE_ERROR_KINDS = {"connection", "timeout", "rate_limit", "server"}


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _dump_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _isinstance_named(value: Any, module: Any, name: str) -> bool:
    cls = getattr(module, name, None)
    return isinstance(value, cls) if cls is not None else False


def _error_payload_fields(value: Any) -> tuple[Optional[str], Optional[str]]:
    payload = getattr(value, "body", None) or getattr(value, "error", None)
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            payload = error
        return _field(payload, "type"), _field(payload, "code")
    return _field(value, "type"), _field(value, "code")


def _kind_from_status_code(status_code: Optional[int]) -> Optional[ProviderErrorKind]:
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


def _status_code(value: Any) -> Optional[int]:
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
    if "server" in lowered or "overloaded" in lowered or "5xx" in lowered:
        return "server"
    return "unknown"


def _openai_error_info(exc: Exception, *, model: str) -> ProviderErrorInfo:
    import openai

    status_code = _status_code(getattr(exc, "status_code", None))
    request_id = getattr(exc, "request_id", None)
    provider_error_type, provider_error_code = _error_payload_fields(exc)

    if _isinstance_named(exc, openai, "RateLimitError"):
        kind: ProviderErrorKind = "rate_limit"
    elif _isinstance_named(exc, openai, "APITimeoutError"):
        kind = "timeout"
    elif _isinstance_named(exc, openai, "APIConnectionError"):
        kind = "connection"
    elif _isinstance_named(exc, openai, "AuthenticationError"):
        kind = "authentication"
    elif _isinstance_named(exc, openai, "PermissionDeniedError"):
        kind = "permission"
    elif _isinstance_named(exc, openai, "BadRequestError"):
        kind = "bad_request"
    elif _isinstance_named(exc, openai, "NotFoundError"):
        kind = "not_found"
    elif _isinstance_named(exc, openai, "ConflictError"):
        kind = "conflict"
    elif _isinstance_named(exc, openai, "UnprocessableEntityError"):
        kind = "unprocessable"
    elif _isinstance_named(exc, openai, "InternalServerError"):
        kind = "server"
    else:
        kind = _kind_from_status_code(status_code) or _kind_from_error_text(str(exc))

    return ProviderErrorInfo(
        provider="openai",
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


class OpenAIResponsesAdapter:
    """Provider adapter for OpenAI Responses function calling."""

    name = "openai"

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client

    def _client_for(
        self,
        project_id: Optional[str],
        workspace_id: Optional[str] = None,
    ) -> Any:
        if self._client is not None:
            return self._client
        responses_client = import_module("app.providers.openai.responses")
        return responses_client.get_client(
            project_id=project_id,
            workspace_id=workspace_id,
        )

    def compile_tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        compiled: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, (LocalToolSpec, McpProxyToolSpec)):
                compiled.append(function_schema(tool))
            elif isinstance(tool, ProviderToolSpec):
                openai_tool = tool.metadata.get("openai_tool")
                if isinstance(openai_tool, dict):
                    compiled.append(dict(openai_tool))
                else:
                    raise ValueError(
                        f"Provider-hosted tool {tool.name!r} has no OpenAI schema"
                    )
            else:
                raise ValueError(f"Unsupported OpenAI tool kind: {tool.kind}")
        return compiled

    def run_turn(self, request: RunRequest) -> RunResult:
        params = self._create_params(request)
        try:
            response = self._client_for(
                request.project_id,
                request.workspace_id,
            ).responses.create(**params)
        except Exception as exc:
            return _provider_error_result(_openai_error_info(exc, model=request.model))
        return self.normalize_response(
            response,
            model_fallback=request.model,
            output_model=request.output_model,
        )

    def stream_turn(self, request: RunRequest) -> Iterator[RunEvent]:
        params = self._create_params(request)
        argument_deltas: dict[str, list[str]] = {}
        function_items: dict[str, dict[str, Any]] = {}
        emitted_tool_call_ids: set[str] = set()
        try:
            stream = self._client_for(
                request.project_id,
                request.workspace_id,
            ).responses.create(
                **params,
                stream=True,
            )
            for event in stream:
                event_type = str(_field(event, "type", ""))
                if event_type == "response.output_item.added":
                    item = _field(event, "item", {}) or {}
                    if str(_field(item, "type", "")) == "function_call":
                        item_id = str(
                            _field(item, "id", "")
                            or _field(item, "call_id", "")
                            or _field(event, "output_index", "")
                        )
                        function_items[item_id] = self._to_dict(item)
                elif event_type in {"response.output_text.delta", "response.text.delta"}:
                    delta = str(_field(event, "delta", ""))
                    yield RunEvent(type="text_delta", data={"delta": delta})
                elif event_type == "response.function_call_arguments.delta":
                    item_id = str(
                        _field(event, "item_id", "")
                        or _field(event, "call_id", "")
                        or _field(event, "output_index", "")
                    )
                    delta = str(_field(event, "delta", ""))
                    argument_deltas.setdefault(item_id, []).append(delta)
                elif event_type == "response.function_call_arguments.done":
                    item_id = str(
                        _field(event, "item_id", "")
                        or _field(event, "call_id", "")
                        or _field(event, "output_index", "")
                    )
                    item = function_items.get(item_id, {})
                    call_id = str(_field(event, "call_id") or _field(item, "call_id") or "")
                    if call_id:
                        emitted_tool_call_ids.add(call_id)
                    yield RunEvent(
                        type="tool_call",
                        data={
                            "call_id": call_id,
                            "name": _field(event, "name") or _field(item, "name"),
                            "arguments": _field(event, "arguments")
                            or "".join(argument_deltas.get(item_id, [])),
                        },
                    )
                elif event_type == "response.error":
                    yield RunEvent(type="error", data=self._to_dict(event))
                elif event_type in _TERMINAL_RESPONSE_EVENTS:
                    response = _field(event, "response")
                    if response is not None:
                        normalized = self.normalize_response(
                            response,
                            model_fallback=request.model,
                            output_model=request.output_model,
                        )
                        for normalized_event in normalized.events:
                            if (
                                normalized_event.type == "tool_call"
                                and str(normalized_event.data.get("call_id") or "")
                                in emitted_tool_call_ids
                            ):
                                continue
                            if normalized_event.type == "final":
                                yield RunEvent(
                                    type="final",
                                    data=final_event_data(
                                        normalized,
                                        normalized_event.data,
                                    ),
                                )
                                continue
                            yield normalized_event
                    elif event_type != "response.completed":
                        event_error = self._terminal_event_error_result(
                            event,
                            event_type=event_type,
                            model=request.model,
                        )
                        yield event_error.events[0]
                        yield RunEvent(
                            type="final",
                            data=final_event_data(
                                event_error,
                                event_error.events[-1].data,
                            ),
                        )
        except Exception as exc:
            result = _provider_error_result(_openai_error_info(exc, model=request.model))
            error_event = result.events[0]
            final_event = result.events[-1]
            yield error_event
            yield RunEvent(
                type="final",
                data=final_event_data(result, final_event.data),
            )

    def _create_params(self, request: RunRequest) -> dict[str, Any]:
        self._preflight_request(request)
        if request.output_model is not None and request.tools:
            raise ValueError(
                "OpenAI structured output mode is only supported for no-tool runs; "
                "use a typed terminating tool for agent loops"
            )
        params: dict[str, Any] = {
            "model": request.model,
            "instructions": self._system_prompt(request),
            "input": self._input_items(request),
            "tools": self.compile_tools(request.tools) if request.tools else None,
            "max_output_tokens": request.limits.max_output_tokens,
            "temperature": request.limits.temperature,
            "metadata": self._metadata(request),
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        tool_choice = self._tool_choice(request)
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        if request.output_model is not None and not request.tools:
            params["text"] = response_format(request.output_model)
        return {key: value for key, value in params.items() if value is not None}

    def _preflight_request(self, request: RunRequest) -> None:
        if request.tool_choice is None:
            return
        if request.tool_choice.type in {"any", "tool"} and not request.tools:
            raise ValueError(
                f"OpenAI tool_choice={request.tool_choice.type!r} requires tools"
            )
        if request.tool_choice.type != "tool":
            return
        tool_names = {tool.name for tool in request.tools}
        if request.tool_choice.name not in tool_names:
            raise ValueError(
                f"OpenAI tool_choice requested unavailable tool "
                f"{request.tool_choice.name!r}"
            )

    def count_tokens(self, text: str, *, model: Optional[str] = None) -> int:
        # OpenAI does not expose an exact Responses count endpoint through the
        # local SDK surface. Keep this deterministic fallback for budgeting;
        # domain chunking already uses tiktoken where exact local speed matters.
        return max(1, len(text) // 4)

    def normalize_response(
        self,
        response: Any,
        *,
        model_fallback: str,
        output_model: Optional[type[Any]] = None,
    ) -> RunResult:
        output_items = list(_field(response, "output", []) or [])
        text_parts: list[str] = []
        content: list[Any] = []
        tool_calls: list[ToolCall] = []
        refusal: Optional[str] = None

        for item in output_items:
            item_type = str(_field(item, "type", ""))
            if item_type == "function_call":
                call_id = str(_field(item, "call_id", "") or _field(item, "id", ""))
                raw_arguments = _field(item, "arguments", "{}")
                try:
                    arguments = json.loads(raw_arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                name = str(_field(item, "name", ""))
                tool_call = ToolCall(
                    call_id=call_id,
                    provider_call_id=call_id,
                    name=name,
                    arguments=arguments,
                    provider_metadata={"raw_arguments": raw_arguments},
                )
                tool_calls.append(tool_call)
                content.append(
                    ToolCallPart(
                        call_id=call_id,
                        provider_call_id=call_id,
                        name=name,
                        arguments=arguments,
                    )
                )
                continue

            if item_type == "message":
                for part in list(_field(item, "content", []) or []):
                    part_type = str(_field(part, "type", ""))
                    if part_type in {"output_text", "text"}:
                        text = str(_field(part, "text", ""))
                        text_parts.append(text)
                        content.append(TextPart(text=text))
                    elif part_type == "refusal":
                        refusal = str(_field(part, "refusal", "") or _field(part, "text", ""))
                        if refusal:
                            text_parts.append(refusal)
                            content.append(TextPart(text=refusal))
                    else:
                        content.append(
                            ProviderMetadataPart(
                                provider=self.name,
                                values=self._to_dict(part),
                            )
                        )
                continue

            content.append(
                ProviderMetadataPart(provider=self.name, values=self._to_dict(item))
            )

        usage = self._usage(_field(response, "usage", {}) or {})
        response_id = str(_field(response, "id", "") or "")
        model = str(_field(response, "model", "") or model_fallback)
        provider_status = str(_field(response, "status", "") or "")
        error = self._response_error(response, provider_status)
        error_info = self._response_error_info(
            response,
            provider_status=provider_status,
            model=model,
            response_id=response_id,
            message=error,
        )
        if error or provider_status in _ERROR_RESPONSE_STATUSES:
            status = "error"
        else:
            status = "requires_tools" if tool_calls else "complete"
        text = "\n".join(part for part in text_parts if part)
        structured = self._structured_result(
            text=text,
            refusal=refusal,
            output_model=output_model,
            raw=response,
        )
        events: list[RunEvent] = [
            RunEvent(
                type="tool_call",
                data={"call_id": call.call_id, "name": call.name},
            )
            for call in tool_calls
        ]
        if error:
            events.append(
                RunEvent(
                    type="error",
                    data={
                        "message": error,
                        "response_id": response_id,
                        "status": provider_status,
                        "error_info": error_info.model_dump(mode="json")
                        if error_info
                        else None,
                    },
                )
            )
        final_data = {"text": text, "status": status}
        if error:
            final_data["error"] = error
        if error_info:
            final_data["error_info"] = error_info.model_dump(mode="json")
        events.extend(
            [
                RunEvent(type="usage", data=usage.model_dump(mode="json")),
                RunEvent(type="final", data=final_data),
            ]
        )
        provider_state_values = {"response_id": response_id}
        if provider_status:
            provider_state_values["status"] = provider_status
        return RunResult(
            provider=self.name,
            model=model,
            status=status,
            text=text,
            content=content,
            tool_calls=tool_calls,
            structured=structured,
            usage=usage,
            provider_state=ProviderState(
                provider=self.name,
                values=provider_state_values,
            ),
            provider_request_ids=[response_id] if response_id else [],
            events=events,
            error=error,
            error_info=error_info,
        )

    def _response_error(self, response: Any, provider_status: str) -> Optional[str]:
        error = _field(response, "error")
        if error:
            if isinstance(error, str):
                return error
            message = _field(error, "message") or _field(error, "code") or _field(
                error,
                "type",
            )
            if message:
                return str(message)
            return json.dumps(self._to_dict(error), ensure_ascii=False, default=str)

        incomplete_details = _field(response, "incomplete_details")
        if incomplete_details:
            reason = _field(incomplete_details, "reason") or _field(
                incomplete_details,
                "message",
            )
            if reason:
                return f"OpenAI response {provider_status}: {reason}"
            details = json.dumps(
                self._to_dict(incomplete_details),
                ensure_ascii=False,
                default=str,
            )
            return f"OpenAI response {provider_status}: {details}"

        if provider_status in _ERROR_RESPONSE_STATUSES:
            return f"OpenAI response {provider_status}"
        return None

    def _response_error_info(
        self,
        response: Any,
        *,
        provider_status: str,
        model: str,
        response_id: str,
        message: Optional[str],
    ) -> Optional[ProviderErrorInfo]:
        if not message and provider_status not in _ERROR_RESPONSE_STATUSES:
            return None

        error = _field(response, "error")
        status_code = _status_code(
            _field(error, "status_code") or _field(response, "status_code")
        )
        provider_error_type = _field(error, "type")
        provider_error_code = _field(error, "code")
        kind = self._response_error_kind(
            provider_status=provider_status,
            status_code=status_code,
            provider_error_type=str(provider_error_type) if provider_error_type else None,
            provider_error_code=str(provider_error_code) if provider_error_code else None,
            message=message or "",
        )
        return ProviderErrorInfo(
            provider=self.name,
            model=model,
            kind=kind,
            message=message or f"OpenAI response {provider_status or 'failed'}",
            status_code=status_code,
            provider_error_type=str(provider_error_type) if provider_error_type else None,
            provider_error_code=str(provider_error_code) if provider_error_code else None,
            request_id=response_id or None,
            retryable=kind in _RETRYABLE_ERROR_KINDS,
            raw=_jsonable(self._to_dict(response)),
        )

    def _response_error_kind(
        self,
        *,
        provider_status: str,
        status_code: Optional[int],
        provider_error_type: Optional[str],
        provider_error_code: Optional[str],
        message: str,
    ) -> ProviderErrorKind:
        if provider_status == "incomplete":
            return "incomplete"
        if provider_status == "cancelled":
            return "cancelled"
        status_kind = _kind_from_status_code(status_code)
        if status_kind is not None:
            return status_kind
        joined = " ".join(
            str(item)
            for item in (provider_error_type, provider_error_code, message)
            if item
        )
        return _kind_from_error_text(joined)

    def _terminal_event_error_result(
        self,
        event: Any,
        *,
        event_type: str,
        model: str,
    ) -> RunResult:
        error = _field(event, "error")
        message = _field(error, "message") or _field(event, "message") or event_type
        provider_status = event_type.replace("response.", "")
        kind = self._response_error_kind(
            provider_status=provider_status,
            status_code=_status_code(_field(error, "status_code")),
            provider_error_type=str(_field(error, "type"))
            if _field(error, "type")
            else None,
            provider_error_code=str(_field(error, "code"))
            if _field(error, "code")
            else None,
            message=str(message),
        )
        info = ProviderErrorInfo(
            provider=self.name,
            model=model,
            kind=kind,
            message=str(message),
            status_code=_status_code(_field(error, "status_code")),
            provider_error_type=str(_field(error, "type"))
            if _field(error, "type")
            else None,
            provider_error_code=str(_field(error, "code"))
            if _field(error, "code")
            else None,
            retryable=kind in _RETRYABLE_ERROR_KINDS,
            raw=_jsonable(self._to_dict(event)),
        )
        return _provider_error_result(info)

    def _structured_result(
        self,
        *,
        text: str,
        refusal: Optional[str],
        output_model: Optional[type[Any]],
        raw: Any,
    ) -> Optional[StructuredResult]:
        if refusal:
            return StructuredResult(
                status="refusal",
                refusal=refusal,
                raw=self._to_dict(raw),
            )
        if output_model is None:
            return None
        try:
            parsed_json = json.loads(text or "{}")
            parsed = output_model.model_validate(parsed_json)
        except Exception as exc:
            return StructuredResult(
                status="invalid",
                error=str(exc),
                raw=self._to_dict(raw),
            )
        return StructuredResult(
            status="parsed",
            parsed=parsed.model_dump(mode="json"),
            raw=self._to_dict(raw),
        )

    def _input_items(self, request: RunRequest) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            message_content: list[dict[str, Any]] = []

            def flush_message() -> None:
                if not message_content:
                    return
                role = "assistant" if message.role == "assistant" else "user"
                items.append({"role": role, "content": list(message_content)})
                message_content.clear()

            for part in message.content:
                if isinstance(part, TextPart):
                    message_content.append({"type": "input_text", "text": part.text})
                elif isinstance(part, MediaPart):
                    message_content.append(self._media_input(part))
                elif isinstance(part, ToolCallPart):
                    flush_message()
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": part.provider_call_id or part.call_id,
                            "name": part.name,
                            "arguments": json.dumps(part.arguments, ensure_ascii=False),
                        }
                    )
                elif isinstance(part, ToolResultPart):
                    flush_message()
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": part.call_id,
                            "output": _dump_output(part.content),
                        }
                    )
                elif (
                    isinstance(part, ProviderMetadataPart)
                    and part.provider == self.name
                    and self._is_replayable_provider_item(part.values)
                ):
                    flush_message()
                    items.append(dict(part.values))
            flush_message()
        return items

    def _is_replayable_provider_item(self, values: dict[str, Any]) -> bool:
        """Return true only for OpenAI output items that are valid continuation input."""
        return values.get("type") == "reasoning"

    def _media_input(self, part: MediaPart) -> dict[str, Any]:
        if part.kind == "image":
            payload: dict[str, Any] = {
                "type": "input_image",
                "detail": part.detail,
            }
            if part.file_id:
                payload["file_id"] = part.file_id
            elif part.url:
                payload["image_url"] = part.url
            elif part.data:
                payload["image_url"] = f"data:{part.media_type};base64,{part.data}"
            else:
                raise ValueError("Image media part has no data, url, or file_id")
            return payload

        if part.kind == "document":
            payload = {"type": "input_file"}
            if part.filename or part.title:
                payload["filename"] = part.filename or part.title
            if part.file_id:
                payload["file_id"] = part.file_id
            elif part.url:
                payload["file_url"] = part.url
            elif part.data:
                payload["file_data"] = part.data
            else:
                raise ValueError("Document media part has no data, url, or file_id")
            return payload

        raise ValueError(f"Unsupported media kind for OpenAI: {part.kind}")

    def _usage(self, usage_data: Any) -> Usage:
        input_details = _field(usage_data, "input_tokens_details", {}) or {}
        output_details = _field(usage_data, "output_tokens_details", {}) or {}
        cached_tokens = int(_field(input_details, "cached_tokens", 0) or 0)
        reasoning_tokens = int(_field(output_details, "reasoning_tokens", 0) or 0)
        provider_units: dict[str, int | float] = {}
        if cached_tokens:
            provider_units["cached_tokens"] = cached_tokens
        if reasoning_tokens:
            provider_units["reasoning_tokens"] = reasoning_tokens
        return Usage(
            input_tokens=int(_field(usage_data, "input_tokens", 0) or 0),
            output_tokens=int(_field(usage_data, "output_tokens", 0) or 0),
            cache_read_input_tokens=cached_tokens,
            provider_units=provider_units,
        )

    def _system_prompt(self, request: RunRequest) -> Optional[str]:
        system_parts: list[str] = []
        if request.system_prompt:
            system_parts.append(request.system_prompt)
        for message in request.messages:
            if message.role != "system":
                continue
            system_parts.extend(
                part.text for part in message.content if isinstance(part, TextPart)
            )
        return "\n\n".join(system_parts) or None

    def _metadata(self, request: RunRequest) -> dict[str, str]:
        metadata = {
            key: str(value)
            for key, value in {
                "project_id": request.project_id,
                "workspace_id": request.workspace_id,
                "chat_id": request.chat_id,
                "purpose": request.purpose,
            }.items()
            if value is not None
        }
        for key, value in request.metadata.items():
            if isinstance(value, (str, int, float, bool)):
                metadata[key] = str(value)
        return metadata

    def _tool_choice(self, request: RunRequest) -> Any:
        if request.tool_choice is not None:
            if request.tool_choice.type == "auto":
                return "auto"
            if request.tool_choice.type == "any":
                return "required"
            if request.tool_choice.type == "none":
                return "none"
            if request.tool_choice.type == "tool":
                return {"type": "function", "name": request.tool_choice.name}
        value = request.metadata.get("tool_choice") or request.metadata.get(
            "anthropic_tool_choice"
        )
        if not isinstance(value, dict):
            return value if value in {"auto", "none", "required"} else None
        choice_type = value.get("type")
        if choice_type == "any":
            return "required"
        if choice_type == "auto":
            return "auto"
        if choice_type == "tool" and isinstance(value.get("name"), str):
            return {"type": "function", "name": value["name"]}
        return None

    def _to_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json")
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return {"value": value}


openai_responses_adapter = OpenAIResponsesAdapter()
