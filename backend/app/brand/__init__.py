"""
Brand domain root.

Charter (NBB-104): Brand config and brand asset ownership. Owns brand asset
metadata, project brand configuration, and the surfaces that studio and other
domains call to resolve brand context.

Allowed imports:
- `api/` route modules and `studio/` (for design/marketing items) import this
  package's public surface.
- This package may depend on `providers/` (storage) and `auth/` for access
  checks.
- This package must not reach into another domain's internals.

Migration source: `backend/app/services/data_services/` currently owns the
brand stores; moves are owned by `NBB-209D`.
"""
