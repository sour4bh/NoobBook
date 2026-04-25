"""
Background chat auto-naming.

After the first user message in a chat, generate a 1-5 word title via Haiku
and update `chats.title`. Runs as a background task so the response is not
blocked. Triggered from `ChatLoop._run_message_flow` once the assistant
message is stored.
"""
import logging
from typing import Any, Dict

from app.background.tasks import task_service
from app.chat.store import chat_service
from app.services.ai_services.chat_naming_service import chat_naming_service


logger = logging.getLogger(__name__)


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
    )


def _generate_and_update_chat_title(
    project_id: str,
    chat_id: str,
    user_message: str,
) -> None:
    """Generate and update chat title in background."""
    try:
        new_title = chat_naming_service.generate_title(user_message, project_id=project_id)
        if new_title:
            chat_service.update_chat(project_id, chat_id, {"title": new_title})
    except Exception as e:
        logger.error("Failed to auto-name chat %s: %s", chat_id, e)
