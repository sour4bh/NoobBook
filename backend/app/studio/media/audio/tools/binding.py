"""Executable tool bindings for audio script generation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.media.audio.tool import studio_audio_executor


def bind_audio_tools(
    specs: Iterable[ToolSpec],
    *,
    project_id: str,
    job_id: str,
    context: dict[str, Any],
) -> list[ToolSpec]:
    """Attach audio source-reading and script-writing handlers."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _runtime_context: Any) -> ToolOutput:
            result, completed = studio_audio_executor.dispatch(
                tool_name=tool_name,
                tool_input=value.model_dump(mode="json", exclude_none=True),
                project_id=project_id,
                job_id=job_id,
            )
            if "This is the last batch" in result:
                context["last_batch_seen"] = True
            if "FULL SOURCE CONTENT" in result:
                context["full_content_seen"] = True
            if completed:
                context["completed"] = True
            return ToolOutput(
                content=result,
                is_error=result.startswith("Error:"),
            )

        return handler

    return bind_local_tools(
        list(specs),
        {
            "read_source_content": dispatch("read_source_content"),
            "write_script_section": dispatch("write_script_section"),
        },
    )
