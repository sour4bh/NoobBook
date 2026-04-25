"""
Chat-owned memory invocation surface.

The `store_memory` tool returns immediately and queues a background merge via
`memory_executor.execute`. This module is the public seam chat code calls
into; the executor's domain home is `app.chat.memory.store` after NBB-303.
"""
from typing import Any, Dict, Optional

from app.chat.memory.store import memory_executor


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
