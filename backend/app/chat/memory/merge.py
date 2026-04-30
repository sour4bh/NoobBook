"""Merge chat memory updates and persist them through the project store."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.agents.runtime import (
    bind_local_tools,
    echo_input,
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    run_with_provider,
)
from app.agents.runtime.tool import ToolSpec
from app.projects.store import DEFAULT_USER_ID, project_service

logger = logging.getLogger(__name__)

_tool_def: Optional[Any] = None


def _resolved_user_id(user_id: Optional[str]) -> str:
    return user_id or DEFAULT_USER_ID


def _load_tool_definition() -> Any:
    global _tool_def

    if _tool_def is None:
        _tool_def = tool_loader.load_tool_spec("memory_tools", "manage_memory_tool")
    return _tool_def


def _bind_memory_merge_tools(specs: list[ToolSpec]) -> list[ToolSpec]:
    """Attach the forced save-memory handler for this small internal workflow.

    The static contract stays in `chat/memory/tools/specs.py` so the catalog can
    discover it without importing memory effects. The executable binding is
    colocated here because this domain has one internal-only forced tool.
    """
    return bind_local_tools(
        specs,
        {"save_memory": echo_input},
        terminating_tools={"save_memory"},
    )


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

    prompt = render_prompt(
        "memory",
        {
            "memory_type": memory_type,
            "current_memory": (
                current_memory
                if current_memory
                else "(empty - no existing memory)"
            ),
            "new_memory": new_memory,
            "reason": reason,
        },
        project_id=project_id,
    )
    tool_def = _load_tool_definition()

    try:
        # Forced tool use keeps the merge output structured and avoids parsing
        # free-form model text before writing long-lived memory.
        # The runtime primitive is intentionally provider-neutral; this module
        # supplies the domain meaning through purpose, prompt, and forced tool
        # choice rather than wrapping the model call in a memory-only facade.
        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose="memory_merge",
                system_prompt=prompt.system_prompt,
                messages=[
                    RunMessage(
                        role="user",
                        content=[TextPart(text=prompt.user_message or "")],
                    )
                ],
                tools=_bind_memory_merge_tools([tool_def]),
                tool_choice=ToolChoice(type="tool", name="save_memory"),
                limits=RunLimits(
                    max_tool_turns=1,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
                user_id=_resolved_user_id(user_id),
            )
        )

        tool_inputs = [
            tool_result.content
            for tool_result in result.tool_results
            if tool_result.name == "save_memory"
            and isinstance(tool_result.content, dict)
            and not tool_result.is_error
        ]

        if not tool_inputs:
            logger.error(
                "Memory merge: save_memory tool result not found. Tool results: %s",
                [item.model_dump(mode="json") for item in result.tool_results],
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
                "model": result.model,
                "usage": result.usage.model_dump(mode="json")
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
