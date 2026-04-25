"""
Chat persistence coordination.

Owns the streaming-event emission seam used by the chat loop. Message-row
writes themselves go directly through `app.chat.message.store.message_service`
in the loop (NBB-209A); wrapping each `add_*_message` call here would only
add a pass-through. The single seam that earns its own module is
`emit_event`, which the loop calls at the five contractual points in
NBB-205 Contract 1 and which both the streaming and non-streaming paths
share.
"""
from typing import Any, Callable, Dict, Optional


def emit_event(
    on_event: Optional[Callable[[str, Dict[str, Any]], None]],
    event_name: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a structured event if a callback is registered.

    Event names are the frozen catalog from NBB-205 Contract 1
    (`user_message`, `ping`, `assistant_delta`, `assistant_done`,
    `error`). Adding a sixth requires a DEFERRED.md entry plus a paired
    frontend change.
    """
    if on_event:
        on_event(event_name, payload or {})
