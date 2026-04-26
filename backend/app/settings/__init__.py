"""
Settings domain root.

Charter (NBB-104): App/user settings and the API-key UI backend. Owns settings
read/write, API-key validator ownership, and surfaces for the Settings UI.

Allowed imports:
- `api/` route modules import this package's public surface.
- This package may depend on `providers/` (secret storage, external validator
  clients) and `auth/` for access checks.
- This package must not reach into another domain's internals.

Runtime settings ownership:
- `app.settings.env.EnvService` manages `.env` reads, writes, deletes, and
  reloads.
- `app.settings.validation` owns the API-key validation dispatcher.

Provider validators live under `app.providers`. Connector validator bodies
remain under the legacy `backend/app/services/app_settings/validation/`
package until NBB-807 moves them to their connector homes.
"""
