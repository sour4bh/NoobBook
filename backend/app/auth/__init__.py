"""
Auth domain root.

Charter (NBB-104): Identity, route/service guards, permission policy, and the
user identity store. Owns token validation, query-token policy, project-access
checks, and the surfaces that other domains call to authorize a request.

Allowed imports:
- Other domains may import this package's public surface to resolve identity
  and authorize access.
- This package may depend on `providers/` for runtime primitives (for example
  Supabase auth clients) and on `base/` only for charter-exempt primitives.
- This package must not reach into another domain's internals.

Migration source: auth behavior formerly lived under `backend/app/services/auth/`;
NBB-008 moved the live surface here and NBB-811 keeps services from returning.
"""
