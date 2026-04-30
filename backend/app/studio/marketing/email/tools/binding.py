"""Executable tool bindings for the email template agent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.binding import bind_local_tools
from app.agents.runtime.tool import ToolOutput, ToolSpec
from app.studio.marketing.email.tool import email_tool_executor


def bind_email_tools(
    specs: Iterable[ToolSpec],
    *,
    context: dict[str, Any],
) -> list[ToolSpec]:
    """Attach email executor handlers with generated-image state."""

    def dispatch(tool_name: str):
        def handler(value: BaseModel, _runtime_context: Any) -> ToolOutput | dict[str, Any]:
            tool_input = value.model_dump(mode="json", exclude_none=True)
            result, is_termination = email_tool_executor.dispatch(
                tool_name,
                tool_input,
                context,
            )
            if tool_name == "generate_email_image" and result.get("image_info"):
                context.setdefault("generated_images", []).append(result["image_info"])
            if is_termination:
                return result
            return ToolOutput(
                content=result.get("message", str(result)),
                is_error=isinstance(result, dict) and not result.get("success", True),
            )

        return handler

    return bind_local_tools(
        specs,
        {
            "plan_email_template": dispatch("plan_email_template"),
            "generate_email_image": dispatch("generate_email_image"),
            "write_email_code": dispatch("write_email_code"),
        },
    )
