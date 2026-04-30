"""Executable tool bindings for studio signal activation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime import bind_local_tools
from app.agents.runtime.tool import ToolContext, ToolOutput, ToolSpec
from app.studio.signal import studio_signal_executor


def bind_studio_signal_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    chat_id: str,
) -> list[ToolSpec]:
    """Attach studio signal handlers to static tool specs."""

    def studio_signal(value: BaseModel, context: ToolContext) -> str | ToolOutput:
        tool_input: dict[str, Any] = value.model_dump(mode="json")
        result = studio_signal_executor.emit(
            project_id=project_id,
            chat_id=chat_id,
            signals=tool_input.get("signals", []),
        )
        if result.get("success"):
            return result.get("message", "Studio signals activated")
        return ToolOutput(
            content=result.get("message", "Unknown error"),
            is_error=True,
        )

    return bind_local_tools(
        list(specs),
        {"studio_signal": studio_signal},
    )
