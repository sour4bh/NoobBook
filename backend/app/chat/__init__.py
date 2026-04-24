"""
Chat domain root.

Charter (NBB-104): Chat loop, streaming, memory invocation, and chat
persistence coordination. Owns the agentic loop, chat/message stores, and
chat-invoked tool adapters exposed to Claude.

Allowed imports:
- `api/` route modules import this package's public surface.
- This package may depend on `auth/`, `projects/`, `sources/`, `connectors/`,
  `background/`, and `providers/` through their published surfaces.
- Other domains may import the chat public surface; they must not reach into
  chat internals.

Migration source: `backend/app/services/chat_services/` and
`backend/app/services/tool_executors/` feed this domain; moves are owned by
`NBB-301` through `NBB-304`.
"""
