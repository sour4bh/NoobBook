"""
Brand domain root.

Charter (NBB-104/NBB-1006): Brand config and brand asset ownership. Owns
workspace brand configuration, brand asset metadata, and the surfaces that
studio and other domains call to resolve brand context.

Allowed imports:
- `api/` route modules and `studio/` (for design/marketing items) import this
  package's public surface.
- This package may depend on `providers/` (storage), `workspaces/` for
  workspace ownership, and `auth/` for access checks.
- This package must not reach into another domain's internals.

Migration source: `backend/app/services/data_services/` formerly owned the
brand stores; moves were owned by `NBB-209D`.
"""
