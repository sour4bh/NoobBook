"""Provider selection for the typed runtime."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Mapping, Optional

from app.agents.runtime.contract import ProviderAdapter, RunEvent, RunRequest, RunResult
from app.agents.runtime.run import RuntimeRunner
from app.agents.runtime.tool import ToolSpec


_ADAPTERS: dict[str, tuple[str, str]] = {
    "anthropic": (
        "app.providers.anthropic.adapter",
        "anthropic_adapter",
    ),
    "openai": (
        "app.providers.openai.adapter",
        "openai_responses_adapter",
    ),
}


def get_provider_adapter(
    provider: str,
    adapters: Mapping[str, ProviderAdapter] | None = None,
) -> ProviderAdapter:
    """Return the adapter for a runtime provider name."""
    if adapters and provider in adapters:
        return adapters[provider]

    target = _ADAPTERS.get(provider)
    if target is None:
        raise ValueError(f"Unsupported runtime provider: {provider}")

    module_name, attribute = target
    module = import_module(module_name)
    return getattr(module, attribute)


def run_with_provider(
    request: RunRequest,
    adapters: Mapping[str, ProviderAdapter] | None = None,
) -> RunResult:
    """Run a request through the adapter selected by `request.provider`."""
    adapter = get_provider_adapter(str(request.provider), adapters)
    return RuntimeRunner().run(request, adapter)


def stream_with_provider(
    request: RunRequest,
    adapters: Mapping[str, ProviderAdapter] | None = None,
    *,
    on_event: Optional[Callable[[RunEvent], None]] = None,
    on_text_delta: Optional[Callable[[str], None]] = None,
) -> RunResult:
    """Stream a request through the selected adapter and shared runtime loop."""
    adapter = get_provider_adapter(str(request.provider), adapters)
    return RuntimeRunner().stream(
        request,
        adapter,
        on_event=on_event,
        on_text_delta=on_text_delta,
    )


def compile_tools_for_provider(
    provider: str,
    specs: list[ToolSpec] | tuple[ToolSpec, ...],
    adapters: Mapping[str, ProviderAdapter] | None = None,
) -> list[dict[str, Any]]:
    """Compile provider-neutral tool specs for one provider."""
    adapter = get_provider_adapter(provider, adapters)
    return adapter.compile_tools(list(specs))


def compile_agent_tools_for_provider(
    provider: str,
    specs: tuple[ToolSpec, ...],
    adapters: Mapping[str, ProviderAdapter] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Compile an agent toolset while preserving hosted/local grouping."""
    compiled = compile_tools_for_provider(provider, specs, adapters)
    server_tools: list[dict[str, Any]] = []
    client_tools: list[dict[str, Any]] = []
    for spec, tool in zip(specs, compiled):
        if spec.kind == "provider":
            server_tools.append(tool)
        else:
            client_tools.append(tool)
    return {
        "server_tools": server_tools,
        "client_tools": client_tools,
        "all_tools": [*server_tools, *client_tools],
        "beta_headers": [],
    }
