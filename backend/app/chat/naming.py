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

from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    run_with_provider,
)
from app.background.tasks import task_service
from app.chat.store import chat_service
from app.config.prompt import render_prompt

logger = logging.getLogger(__name__)

def generate_title(
    first_message: str,
    project_id: Optional[str] = None,
) -> Optional[str]:
    """Generate a 1-5 word title for a chat from the first user message."""
    if not first_message or not first_message.strip():
        return None

    try:
        prompt = render_prompt("chat_naming", project_id=project_id)
        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose="chat_naming",
                messages=[
                    RunMessage(role="user", content=[TextPart(text=first_message)])
                ],
                system_prompt=prompt.system_prompt,
                limits=RunLimits(
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
            )
        )
        title = result.text.strip()
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
