"""
ElevenLabs transcription configuration endpoints.

Educational Note: These endpoints provide configuration for real-time
speech-to-text. The actual transcription happens client-side via WebSocket
for lowest latency - we just provide the secure connection details.

Why Client-Side WebSocket?
- Latency: Audio goes directly to ElevenLabs, not through our server
- Scalability: Our server doesn't need to handle audio streaming
- Cost: No bandwidth costs for audio passing through our server

Token-Based Authentication:
- ElevenLabs provides single-use tokens via their REST API
- Token is embedded in WebSocket URL: wss://api.elevenlabs.io/...?token=XXX
- Token expires after 15 minutes
- Frontend requests new token for each recording session

Routes:
- GET /transcription/config - Get WebSocket URL with fresh token
- GET /transcription/status - Check if ElevenLabs is configured
"""
from flask import jsonify, current_app, request
from app.api.transcription import transcription_bp
from app.auth.guards import require_permission
from app.auth.identity import get_request_identity
from app.projects.store import DEFAULT_USER_ID
from app.providers.elevenlabs import TranscriptionService
from app.workspaces.settings import workspace_settings_store
from app.workspaces.store import workspace_store

# Initialize service (lazy loads API key from env)
transcription_service = TranscriptionService()


def _requested_workspace_id() -> str | None:
    header_value = (request.headers.get("X-NoobBook-Workspace-Id") or "").strip()
    if header_value:
        return header_value
    query_value = (request.args.get("workspace_id") or "").strip()
    return query_value or None


def _current_workspace_id() -> str:
    identity = get_request_identity()
    try:
        workspace_id = workspace_settings_store.resolve_workspace_id(
            user_id=identity.user_id,
            email=identity.email,
            requested_workspace_id=_requested_workspace_id(),
        )
    except ValueError:
        return DEFAULT_USER_ID
    if not workspace_store.has_workspace_access(workspace_id, identity.user_id):
        raise PermissionError("Workspace access required")
    return workspace_id


@transcription_bp.route('/transcription/config', methods=['GET'])
@require_permission("chat_features", "voice_input")
@require_permission("integrations", "elevenlabs")
def get_transcription_config():
    """
    Get ElevenLabs configuration for real-time transcription.

    Educational Note: This endpoint generates a single-use token and embeds it
    in the WebSocket URL. The flow is:

    1. Frontend calls this endpoint before recording
    2. We call ElevenLabs API to get single-use token
    3. We return WebSocket URL with token embedded
    4. Frontend connects directly to ElevenLabs WebSocket
    5. Token expires after 15 minutes (request fresh for each session)

    Security Note: The API key never leaves the server. Only the single-use
    token is embedded in the WebSocket URL for authentication. This is a
    common pattern for protecting API credentials while enabling client-side
    real-time features.

    Returns:
        {
            "success": true,
            "websocket_url": "wss://api.elevenlabs.io/v1/...?token=XXX",
            "model_id": "scribe_v1",
            "sample_rate": 16000,
            "encoding": "pcm_s16le"
        }
    """
    try:
        config = transcription_service.get_elevenlabs_config(
            workspace_id=_current_workspace_id()
        )

        return jsonify({
            'success': True,
            **config
        }), 200

    except ValueError as e:
        # API key not configured
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403

    except Exception as e:
        current_app.logger.error(f"Error getting transcription config: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get transcription configuration'
        }), 500


@transcription_bp.route('/transcription/status', methods=['GET'])
@require_permission("chat_features", "voice_input")
@require_permission("integrations", "elevenlabs")
def get_transcription_status():
    """
    Check if ElevenLabs transcription is configured.

    Educational Note: This is a lightweight "health check" endpoint.
    It checks if the ElevenLabs API key is set without:
    - Exposing the actual key
    - Making any external API calls
    - Generating tokens (which have limited uses)

    Use Case: Frontend can call this on load to decide whether to
    show/hide the microphone button. No point showing voice input
    if transcription isn't configured.

    Returns:
        {
            "success": true,
            "configured": true  // or false if API key not set
        }
    """
    try:
        is_configured = transcription_service.is_configured(
            workspace_id=_current_workspace_id()
        )

        return jsonify({
            'success': True,
            'configured': is_configured
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error checking transcription status: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to check transcription status'
        }), 500
