"""
Chat-owned memory invocation surface.

The `store_memory` tool returns immediately and queues a background merge via
`memory_executor.execute`. This module is the public seam chat code calls
into; the executor's domain home is `app.chat.memory.run` (renamed from
`store.py` in NBB-706 to remove the shadow with the public `store` callable).
"""
from typing import Any, Dict, Optional

from app.chat.memory import merge
from app.chat.memory.run import memory_executor


def store(
    project_id: str,
    *,
    user_memory: Optional[str],
    project_memory: Optional[str],
    why_generated: str,
    user_id: Optional[str],
) -> Dict[str, Any]:
    """Invoke the memory tool executor for chat's `store_memory` tool call."""
    return memory_executor.execute(
        project_id=project_id,
        user_memory=user_memory,
        project_memory=project_memory,
        why_generated=why_generated,
        user_id=user_id,
    )


def get_user_memory(user_id: Optional[str] = None) -> Optional[str]:
    return merge.get_user_memory(user_id=user_id)


def get_project_memory(project_id: str, user_id: Optional[str] = None) -> Optional[str]:
    return merge.get_project_memory(project_id, user_id=user_id)


def update_memory(
    memory_type: str,
    new_memory: str,
    reason: str,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    return merge.update_memory(
        memory_type=memory_type,
        new_memory=new_memory,
        reason=reason,
        project_id=project_id,
        user_id=user_id,
    )


def delete_project_memory(project_id: str, user_id: Optional[str] = None) -> bool:
    return merge.delete_project_memory(project_id, user_id=user_id)
