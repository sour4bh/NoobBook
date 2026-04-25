"""
Chat Services - legacy chat orchestration package.

Migration status (NBB-301): The canonical chat entry points are now
`chat.send` and `chat.stream` on the `app.chat` public surface. This package
remains as a temporary import shim for `main_chat_service`, which `chat.loop`
delegates to until NBB-302 splits its internals. NBB-706 removes this
re-export once NBB-302 lands.
"""
from app.services.chat_services.main_chat_service import main_chat_service

__all__ = ["main_chat_service"]
