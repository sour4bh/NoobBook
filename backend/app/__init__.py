"""
Flask application factory for NoobBook.

Educational Note: The application factory pattern allows us to create
multiple app instances with different configurations (dev, test, prod).
This is a Flask best practice for larger applications.

Bootstrap inventory (NBB-208A).
Every line below is a migration touch point; downstream tickets that move
auth, RBAC, project access, Supabase, or integrations must update this file.

1. Config loading
   - `from config import config` pulls the `Config` dict from
     `backend/config.py` (top-level module).
   - Note: `backend/config.py` (plain module exposing a config dict) collides
     with the `backend/app/config/` subpackage. This is a preexisting
     structural issue, flagged (not fixed) per the Decision Log entry dated
     2026-04-24. Renaming `backend/config.py` belongs to a backend-charter
     follow-up ticket; `NBB-208A` must not introduce a rename or shim.
2. Logging setup via `app.utils.logger.setup_logging`.
3. `config[config_name].init_app(app)` runs env-dependent init (directory
   creation, etc.) through the Config class.
4. `ensure_base_directories()` from `app.utils.path_utils` creates runtime
   filesystem paths before routes fire.
5. Flask extensions:
   - `CORS(app, origins=...)` — allowed origins driven by `CORS_ALLOWED_ORIGINS`.
   - `socketio.init_app(app, async_mode=...)` — async mode is gevent in
     production and threading in development (gated by `FLASK_ENV`).
6. Blueprint registration
   - `from app.api import api_bp` at `app.config['API_PREFIX']`.
   - `backend/app/api/` remains the transport boundary (per `NBB-104`).
7. Supabase admin bootstrap
   - `auth_service.bootstrap_admin_from_env()` runs only when
     `is_supabase_enabled()` returns True.
8. Auth enforcement `before_request` hook
   - CORS preflight short-circuits before auth.
   - `is_auth_required()` gates enforcement; `/auth/*` and `/health` are
     exempt.
   - Project-scoped routes (`/projects/{id}/...`) run
     `project_service.has_project_access(...)` — `NBB-107` owns the auth
     test seam; `NBB-204` owns the RLS/data-access rules that back this
     check.
9. `register_error_handlers(app)` registers 400/404/500 JSON handlers.

Observability and deployment boundaries are inventoried separately in
`docs/deployment/observability.md` (NBB-208B). That file names which
observability concerns are cross-cutting (logger bootstrap below),
provider-owned (Opik on the Claude client), background-owned (task
lifecycle logs), or chat-owned (SSE event emission), and lists the
deployment constraints — Gunicorn single-worker, gevent monkey-patch,
nginx SSE/Socket.IO passthrough — that movement tickets must preserve.

Env/service reload semantics.
`backend/app/services/app_settings/env_service.EnvService.reload_env()` calls
`load_dotenv(override=True)` after each `.env` write. Integration services
that cache config (Notion, Jira, Freshdesk, Mixpanel) expose a
`reload_config()` method; `ClaudeService.reload_config()` resets its cached
client so Opik wrapping is re-evaluated on the next call. The settings API is
the caller responsible for invoking these hooks — integration services do
not self-reload. See `backend/app/api/settings/api_keys.py` for the authoritative
validator ↔ reload-hook map.
"""
import os

from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO

# Educational Note (NBB-208A): `config` here is `backend/config.py`, not the
# `backend/app/config/` subpackage. Renaming the top-level module is a
# separate backend-charter follow-up; do not shim here.
from config import config
from app.utils.logger import setup_logging

# Initialize extensions globally but without app context.
# Use gevent in production (for Gunicorn), threading in development (for Werkzeug).
_async_mode = 'gevent' if os.getenv('FLASK_ENV') == 'production' else 'threading'
socketio = SocketIO(cors_allowed_origins="*")


def create_app(config_name='development'):
    """
    Create and configure the Flask application.

    Educational Note: This factory function:
    1. Creates the Flask instance
    2. Loads configuration
    3. Initializes extensions
    4. Registers blueprints (route modules)
    """
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])
    setup_logging(app.config.get('LOG_LEVEL', 'DEBUG'))
    config[config_name].init_app(app)

    # Ensure base directories exist before any routes access them
    from app.utils.path_utils import ensure_base_directories
    ensure_base_directories()

    # Initialize extensions with app context
    CORS(app,
         origins=app.config['CORS_ALLOWED_ORIGINS'],
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
    socketio.init_app(app, async_mode=_async_mode)

    # Register blueprints (modular route handlers)
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix=app.config['API_PREFIX'])

    # Bootstrap admin (optional) when env vars are provided
    from app.services.integrations.supabase import auth_service, is_supabase_enabled
    if is_supabase_enabled():
        auth_service.bootstrap_admin_from_env()

    # Optional auth enforcement (RBAC)
    from app.auth.identity import get_request_identity, is_auth_required

    @app.before_request
    def enforce_auth():
        # Skip CORS preflight requests
        if request.method == 'OPTIONS':
            return None

        if not is_auth_required():
            return None

        path = request.path
        api_prefix = app.config.get('API_PREFIX', '/api/v1')

        if not path.startswith(api_prefix):
            return None

        # Allow auth and health endpoints without authentication
        if path.startswith(f"{api_prefix}/auth") or path == f"{api_prefix}/health":
            return None

        identity = get_request_identity()
        if not identity.is_authenticated:
            return {"success": False, "error": "Authentication required"}, 401

        # Enforce per-project access for project-scoped routes
        project_prefix = f"{api_prefix}/projects/"
        if path.startswith(project_prefix):
            remainder = path[len(project_prefix):]
            project_id = remainder.split("/", 1)[0] if remainder else ""
            if project_id:
                from app.projects.store import project_service
                if not project_service.has_project_access(project_id, identity.user_id):
                    return {"success": False, "error": "Project not found"}, 404

        return None

    # Register error handlers
    register_error_handlers(app)

    # Log successful initialization
    app.logger.info(f"✅ {app.config['APP_NAME']} backend initialized successfully")

    return app


def register_error_handlers(app):
    """
    Register global error handlers for the application.

    Educational Note: Centralized error handling ensures consistent
    error responses across all endpoints.
    """
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Resource not found"}, 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal error: {error}")
        return {"error": "Internal server error"}, 500

    @app.errorhandler(400)
    def bad_request(error):
        return {"error": "Bad request"}, 400
