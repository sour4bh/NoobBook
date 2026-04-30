"""Small helpers for building executable runtime tool specs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from app.agents.runtime.tool import LocalToolSpec, ToolContext, ToolHandler, ToolSpec


def echo_input(value: BaseModel, context: ToolContext) -> dict[str, Any]:
    """Return validated tool input as JSON-compatible data."""
    return value.model_dump(mode="json")


def bind_local_tools(
    specs: tuple[ToolSpec, ...] | list[ToolSpec],
    handlers: Mapping[str, ToolHandler],
    *,
    terminating_tools: Iterable[str] = (),
) -> list[ToolSpec]:
    """Attach per-run handlers to matching local tool specs."""
    bound: list[ToolSpec] = []
    terminating = set(terminating_tools)
    for spec in specs:
        if isinstance(spec, LocalToolSpec) and spec.name in handlers:
            updates: dict[str, Any] = {"handler": handlers[spec.name]}
            if spec.name in terminating:
                updates["terminates_run"] = True
            bound.append(spec.model_copy(update=updates))
        else:
            bound.append(spec)
    return bound
