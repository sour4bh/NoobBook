"""Merge chat memory updates and persist them through the project store."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.config.prompt_loader import prompt_loader
from app.config.tool_loader import tool_loader
from app.providers.anthropic import response_parser
from app.projects.store import DEFAULT_USER_ID, project_service
from app.services.integrations.claude import claude_service

logger = logging.getLogger(__name__)

_prompt_config: Optional[Dict[str, Any]] = None
_tool_def: Optional[Dict[str, Any]] = None


def _resolved_user_id(user_id: Optional[str]) -> str:
    return user_id or DEFAULT_USER_ID


def _get_prompt_config() -> Dict[str, Any]:
    global _prompt_config

    if _prompt_config is None:
        _prompt_config = prompt_loader.get_prompt_config("memory")
        if _prompt_config is None:
            raise ValueError("memory_prompt.json not found in data/prompts/")
    return _prompt_config


def _load_tool_definition() -> Dict[str, Any]:
    global _tool_def

    if _tool_def is None:
        _tool_def = tool_loader.load_tool("memory_tools", "manage_memory_tool")
    return _tool_def


def get_user_memory(user_id: Optional[str] = DEFAULT_USER_ID) -> Optional[str]:
    try:
        return project_service.get_user_memory(user_id=_resolved_user_id(user_id))
    except Exception:
        logger.exception("Error reading user memory")
        return None


def get_project_memory(
    project_id: str,
    user_id: Optional[str] = DEFAULT_USER_ID,
) -> Optional[str]:
    try:
        memory_data = project_service.get_project_memory(
            project_id,
            user_id=_resolved_user_id(user_id),
        )
        if memory_data:
            return memory_data.get("memory")
        return None
    except Exception:
        logger.exception("Error reading project memory")
        return None


def _save_user_memory(
    memory: str,
    user_id: Optional[str] = DEFAULT_USER_ID,
) -> bool:
    try:
        return project_service.update_user_memory(
            memory,
            user_id=_resolved_user_id(user_id),
        )
    except Exception:
        logger.exception("Error saving user memory")
        return False


def _save_project_memory(
    project_id: str,
    memory: str,
    user_id: Optional[str] = DEFAULT_USER_ID,
) -> bool:
    try:
        memory_data = {
            "memory": memory,
            "updated_at": datetime.now().isoformat()
        }
        return project_service.update_project_memory(
            project_id,
            memory_data,
            user_id=_resolved_user_id(user_id),
        )
    except Exception:
        logger.exception("Error saving project memory")
        return False


def _build_user_message(
    config: Dict[str, Any],
    memory_type: str,
    current_memory: str,
    new_memory: str,
    reason: str,
) -> str:
    template = config.get("user_message", "")

    return template.format(
        memory_type=memory_type,
        current_memory=current_memory if current_memory else "(empty - no existing memory)",
        new_memory=new_memory,
        reason=reason,
    )


def update_memory(
    memory_type: str,
    new_memory: str,
    reason: str,
    project_id: Optional[str] = None,
    user_id: Optional[str] = DEFAULT_USER_ID,
) -> Dict[str, Any]:
    """Merge and persist user or project memory for chat."""
    if memory_type not in ["user", "project"]:
        return {"success": False, "error": f"Invalid memory_type: {memory_type}"}

    if memory_type == "project" and not project_id:
        return {"success": False, "error": "project_id required for project memory"}
    project_id_for_memory = project_id or ""

    if memory_type == "user":
        current_memory = get_user_memory(user_id=user_id) or ""
    else:
        current_memory = get_project_memory(project_id_for_memory, user_id=user_id) or ""

    config = _get_prompt_config()
    tool_def = _load_tool_definition()
    user_message = _build_user_message(
        config=config,
        memory_type=memory_type,
        current_memory=current_memory,
        new_memory=new_memory,
        reason=reason,
    )

    try:
        # Forced tool use keeps the merge output structured and avoids parsing
        # free-form model text before writing long-lived memory.
        response = claude_service.send_message(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=config.get("system_prompt", ""),
            model=config.get("model"),
            max_tokens=config.get("max_tokens"),
            temperature=config.get("temperature"),
            tools=[tool_def],
            tool_choice={"type": "tool", "name": "save_memory"},
            project_id=project_id,
        )

        tool_inputs = response_parser.extract_tool_inputs(
            response,
            "save_memory",
        )

        if not tool_inputs:
            logger.error(
                "Memory merge: save_memory tool not found in response. "
                "Content blocks: %s", response.get("content_blocks")
            )
            return {
                "success": False,
                "error": "AI did not use save_memory tool"
            }

        tool_input = tool_inputs[0]
        merged_memory = tool_input.get("memory", "")

        if not merged_memory:
            logger.error(
                "Memory merge: tool called but memory is empty. "
                "Full tool input: %s", tool_input
            )
            merged_memory = f"{current_memory}\n{new_memory}".strip() if current_memory else new_memory
            if len(merged_memory) > 600:
                logger.warning(
                    "Memory merge fallback: concatenated memory may exceed token limit (%d chars)",
                    len(merged_memory),
                )
            logger.info("Memory merge: falling back to concatenation of current + new memory")

        if memory_type == "user":
            saved = _save_user_memory(merged_memory, user_id=user_id)
        else:
            saved = _save_project_memory(project_id_for_memory, merged_memory, user_id=user_id)

        if saved:
            logger.info("Memory updated (%s)", memory_type)
            return {
                "success": True,
                "memory_type": memory_type,
                "memory": merged_memory,
                "previous_memory": current_memory,
                "model": response.get("model"),
                "usage": response.get("usage")
            }
        return {
            "success": False,
            "error": "Failed to save memory to Supabase"
        }

    except Exception as e:
        logger.exception("Error updating memory")
        return {
            "success": False,
            "error": str(e)
        }


def delete_project_memory(
    project_id: str,
    user_id: Optional[str] = DEFAULT_USER_ID,
) -> bool:
    try:
        return project_service.update_project_memory(
            project_id,
            {},
            user_id=_resolved_user_id(user_id),
        )
    except Exception:
        logger.exception("Error clearing project memory")
        return False
