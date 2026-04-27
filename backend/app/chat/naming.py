"""
Background chat auto-naming.

After the first user message in a chat, generate a 1-5 word title via Haiku
and update `chats.title`. Runs as a background task so the response is not
blocked. Triggered from `ChatLoop._run_message_flow` once the assistant
message is stored.

Title generation lives here directly. The legacy
`services/ai_services/chat_naming_service.py` class was removed in NBB-706;
its `_prompt_config` lazy cache moved here as a module-private variable.
"""
import logging
from typing import Any, Dict, Optional

import app.providers.anthropic.response_parser
from app.background.tasks import task_service
from app.chat.store import chat_service
from app.config.prompt import prompt_loader
from app.providers.anthropic import claude_service

logger = logging.getLogger(__name__)

_prompt_config: Optional[Dict[str, Any]] = None


def _get_prompt_config() -> Dict[str, Any]:
    """Load and cache the chat-naming prompt config."""
    global _prompt_config
    if _prompt_config is None:
        cfg = prompt_loader.get_prompt_config("chat_naming")
        if cfg is None:
            raise ValueError("chat_naming_prompt.json not registered or missing")
        _prompt_config = cfg
    return _prompt_config


def generate_title(
    first_message: str,
    project_id: Optional[str] = None,
) -> Optional[str]:
    """Generate a 1-5 word title for a chat from the first user message."""
    if not first_message or not first_message.strip():
        return None

    try:
        config = _get_prompt_config()
        response = claude_service.send_message(
            messages=[{"role": "user", "content": first_message}],
            system_prompt=config.get("system_prompt", ""),
            model=config.get("model"),
            max_tokens=config.get("max_tokens"),
            temperature=config.get("temperature"),
            project_id=project_id,
        )
        title = app.providers.anthropic.response_parser.extract_text(response).strip()
        if not title:
            return None
        title = title.strip("\"'")
        words = title.split()
        if len(words) > 5:
            title = " ".join(words[:5])
        return title
    except Exception:
        logger.exception("Error generating chat title")
        return None


def submit_naming_task(
    chat: Dict[str, Any],
    project_id: str,
    chat_id: str,
    user_message_text: str,
) -> None:
    """Queue background naming on the first user message of a chat.

    `chat` is the row read at the top of the message flow; the
    `message_count` it carries is the pre-write count, which is why the
    "first message" gate works after the assistant message is stored.
    """
    if chat.get("message_count", 0) != 0:
        return
    task_service.submit_task(
        "chat_naming",
        chat_id,
        _generate_and_update_chat_title,
        project_id,
        chat_id,
        user_message_text,
        owner_project_id=project_id,
    )


def _generate_and_update_chat_title(
    project_id: str,
    chat_id: str,
    user_message: str,
) -> None:
    """Generate and update chat title in background."""
    try:
        new_title = generate_title(user_message, project_id=project_id)
        if new_title:
            chat_service.update_chat(project_id, chat_id, {"title": new_title})
    except Exception as exc:
        logger.error("Failed to auto-name chat %s: %s", chat_id, exc)
