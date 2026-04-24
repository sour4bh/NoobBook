"""
App Settings - Services for managing application configuration.

Educational Note: This folder contains services related to application settings:
- EnvService: Manages .env file operations (read, write, delete keys)
- ValidationService: Validates API keys by making test requests to each service

The validation folder contains individual validators for each service,
keeping the code modular and easy to maintain.

Migration status (NBB-208A).
This package is the legacy location. The `settings/` charter at
`backend/app/settings/__init__.py` (authored in `NBB-104`) names this package
as the migration source. No code moves in `NBB-208A`; the owning destinations
are captured in the validator-ownership decision map inside
`backend/app/api/settings/api_keys.py`.

Env-reload semantics.
- `EnvService.set_key` writes the `.env` file via python-dotenv and assigns
  `os.environ[key]` in-process.
- `EnvService.reload_env` calls `load_dotenv(override=True)` so indirectly
  cached readers see the new value.
- `.env` path is resolved relative to `backend/` via
  `Path(__file__).parent.parent.parent.parent`; any future move of this
  package must preserve that resolution.

Service-reload contract.
- Integration services that cache configuration (Notion, Jira, Freshdesk,
  Mixpanel under `services/integrations/...`, and the Claude client under
  `services/integrations/claude`) expose a `reload_config()` method that
  resets the cache so the next call re-reads from `os.environ`.
- The settings API (`backend/app/api/settings/api_keys.py`) is the single
  caller responsible for invoking these hooks after `reload_env()`.
  Integration services do not self-reload and are not expected to poll `.env`.

Validator ownership.
- `settings/` owns the validate endpoint, `.env` CRUD orchestration, and the
  `ValidationService` facade that routes `key_id`s to individual validators.
- Post-`NBB-206`, raw SDK health-check validators move under `providers/`;
  product-capability validators (Notion, Jira, Freshdesk, Mixpanel) move
  under `connectors/`. See `api_keys.py` for the full map.
"""
from app.services.app_settings.env_service import EnvService
from app.services.app_settings.validation import ValidationService

__all__ = ["EnvService", "ValidationService"]
