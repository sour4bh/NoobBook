"""
Projects domain root.

Charter (NBB-104): Project domain behavior and the project store. Owns project
CRUD, cost accounting, project memory, and project-scoped lookups that other
domains depend on.

Allowed imports:
- Other domains may import this package's public surface to resolve project
  state and cost accounting.
- This package may depend on `providers/` for storage/client primitives and on
  `auth/` for identity/permission checks.
- This package must not reach into another domain's internals.

Migration source: project persistence currently lives under
`backend/app/services/data_services/` and moves in later tickets.
"""
