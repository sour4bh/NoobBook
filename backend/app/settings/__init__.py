"""
Settings domain root.

Charter (NBB-104): App/user settings and the API-key UI backend. Owns settings
read/write, API-key validator ownership, and surfaces for the Settings UI.

Allowed imports:
- `api/` route modules import this package's public surface.
- This package may depend on `providers/` (secret storage, external validator
  clients) and `auth/` for access checks.
- This package must not reach into another domain's internals.

Migration source: `backend/app/services/app_settings/` remains the legacy
location (name mismatch is intentional) until later tickets move behavior
here.
"""
