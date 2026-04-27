"""
API Blueprint initialization.

Charter (NBB-104): `api/` is the transport boundary. Route modules here parse
HTTP input, run auth/permission guards, call domain public surfaces, and format
responses. They do not own product behavior, persistence, or cross-domain
orchestration. Moving route modules into domain packages is tracked by D-001
and is out of scope for this migration.

Allowed imports: domain public surfaces (`auth/`, `projects/`, `chat/`,
`sources/`, `studio/`, `brand/`, `settings/`, `connectors/`, `background/`)
and lightweight Flask-layer helpers. Route modules must not import another
domain's internals.

Blueprint Architecture:
- api_bp: Main API blueprint (registered at /api/v1 in app factory)
  - auth_bp: Authentication (signup, login, logout, session)
  - projects_bp: Project CRUD, costs, memory
  - chats_bp: Chat CRUD operations
  - messages_bp: Message sending (AI interaction)
  - prompts_bp: System prompt management
  - google_bp: Google Drive OAuth and file operations
  - transcription_bp: ElevenLabs speech-to-text config
  - settings_bp: API keys and processing tier config
  - sources_bp: Source upload, processing, citations
  - studio_bp: Studio management and collaboration
  - brand_bp: Brand assets and configuration

Authentication: A before_request hook on api_bp validates JWT tokens
for ALL routes except /auth/* endpoints. This protects every endpoint
without needing @require_auth on each route.
"""
from flask import Blueprint, request, jsonify, g

from app.api.auth.middleware import validate_token  # noqa: E402
from app.auth.identity import get_request_identity, is_auth_required  # noqa: E402

from app.api.auth import auth_bp
from app.api.chats import chats_bp
from app.api.messages import messages_bp
from app.api.prompts import prompts_bp
from app.api.google import google_bp
from app.api.projects import projects_bp
from app.api.transcription import transcription_bp
from app.api.settings import settings_bp
from app.api.sources import sources_bp
from app.api.studio import studio_bp
from app.api.brand import brand_bp

# Create the main API blueprint
api_bp = Blueprint('api', __name__)

# =============================================================================
# Authentication - Protect all routes except /auth/*
# =============================================================================
# Educational Note: before_request runs before every request to any route
# under api_bp. We skip auth endpoints (login, signup, refresh) since those
# are public. All other routes require a valid JWT token.

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Docker/Coolify — no auth required."""
    return {"status": "ok"}, 200


@api_bp.before_request
def authenticate_request():
    """Validate JWT for all API requests except auth endpoints."""
    # Skip CORS preflight requests — browser sends OPTIONS before authenticated requests
    if request.method == 'OPTIONS':
        return None

    # Skip authentication for auth, health, and provider OAuth callback routes.
    if (
        request.path.startswith('/api/v1/auth/')
        or request.path == '/api/v1/health'
        or request.path == '/api/v1/google/callback'
    ):
        return None

    if not is_auth_required():
        identity = get_request_identity()
        g.user_id = identity.user_id
        return None

    user_id = validate_token()

    if not user_id:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    # Attach user_id to request context for use in route handlers
    g.user_id = user_id
    return None


# =============================================================================
# Register Nested Blueprints (Modular)
# =============================================================================
# These blueprints have their own folders with __init__.py and routes.py

# Register nested blueprints with the main api blueprint
# No url_prefix needed - routes already have full paths
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(chats_bp)
api_bp.register_blueprint(messages_bp)
api_bp.register_blueprint(prompts_bp)
api_bp.register_blueprint(google_bp)
api_bp.register_blueprint(projects_bp)
api_bp.register_blueprint(transcription_bp)
api_bp.register_blueprint(settings_bp)
api_bp.register_blueprint(sources_bp)
api_bp.register_blueprint(studio_bp)
api_bp.register_blueprint(brand_bp)
