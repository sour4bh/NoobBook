"""
Connectors root.

Charter (NBB-104): Product-level configured external capabilities, user/project
connection stores, and permission-gated tool surfaces. Connectors wrap a
provider client into a configured product capability (for example Notion,
Jira, Google Drive, MCP). Boundary rules are finalized in `NBB-206`.

Allowed imports:
- Domains (`chat/`, `sources/`, `studio/`, etc.) import connector public
  surfaces to invoke configured capabilities.
- This package may depend on `providers/`, `auth/`, and `projects/`.
- Connectors must not reach into a domain's internals and must not duplicate
  domain behavior; format-specific operations belong in `sources/` and
  studio-owned export behavior belongs in `studio/`.

Migration source: `backend/app/services/integrations/` and parts of
`backend/app/services/tool_executors/` feed this root.
"""
