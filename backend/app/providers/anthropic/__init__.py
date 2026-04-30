"""Anthropic provider public surface.

Exports are lazy so importing parser/adapter helpers does not initialize the
Claude client or any storage-backed runtime dependencies.
"""

from typing import Any

__all__ = [
    "AnthropicMessagesAdapter",
    "anthropic_adapter",
    "ClaudeService",
    "claude_service",
]


def __getattr__(name: str) -> Any:
    if name in {"AnthropicMessagesAdapter", "anthropic_adapter"}:
        from app.providers.anthropic.adapter import (
            AnthropicMessagesAdapter,
            anthropic_adapter,
        )

        values = {
            "AnthropicMessagesAdapter": AnthropicMessagesAdapter,
            "anthropic_adapter": anthropic_adapter,
        }
        return values[name]
    if name in {"ClaudeService", "claude_service"}:
        from app.providers.anthropic.messages import ClaudeService, claude_service

        values = {
            "ClaudeService": ClaudeService,
            "claude_service": claude_service,
        }
        return values[name]
    raise AttributeError(name)
