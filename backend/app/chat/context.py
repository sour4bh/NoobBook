"""
Chat system-prompt assembly.

Composes the per-turn system prompt: today's date, the project's base
prompt, source/memory context, and brand guidelines. Rebuilt on every
message so memory updates and per-chat source selections take effect
immediately.
"""
from datetime import date
from typing import List, Optional

from app.config.brand import brand_context_loader
from app.config.context import context_loader


def build_system_prompt(
    project_id: str,
    base_prompt: str,
    *,
    user_id: Optional[str] = None,
    selected_source_ids: Optional[List[str]] = None,
) -> str:
    """Assemble the chat system prompt for a single Claude turn.

    Order is contractual: today's date first (so Claude can resolve
    relative dates without explicit values), then the project's base
    prompt, then source/memory context, then brand context.
    """
    today_line = f"Today's date: {date.today().isoformat()}"
    parts = [today_line, base_prompt]

    full_context = context_loader.build_full_context(
        project_id, user_id=user_id, selected_source_ids=selected_source_ids
    )
    if full_context:
        parts.append(full_context)

    brand_context = brand_context_loader.load_brand_context(project_id, "chat", user_id=user_id)
    if brand_context:
        parts.append(brand_context)

    return "\n".join(parts)
