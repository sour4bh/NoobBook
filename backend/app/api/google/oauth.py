"""
Google OAuth 2.0 flow endpoints.

Educational Note: OAuth 2.0 is the industry standard for authorization.
It allows users to grant our app access to their Google Drive without
sharing their password.

The OAuth Dance:
1. /google/status  - Check if we're configured and connected
2. /google/auth    - Get the authorization URL (includes signed one-time state)
3. (User visits Google, grants permission)
4. /google/callback - Google redirects here with auth code + state
5. /google/disconnect - Remove stored tokens

Security Considerations:
- Never expose client secret to frontend
- Use HTTPS in production for callback URL
- Store refresh tokens securely in Supabase (per-user)
- Handle token expiration gracefully
- State parameter carries a signed one-time nonce for multi-user support

Routes:
- GET  /google/status     - Check configuration and connection
- GET  /google/auth       - Get OAuth authorization URL
- GET  /google/callback   - Handle OAuth callback (redirects)
- POST /google/disconnect - Remove stored tokens
"""
from urllib.parse import urlencode

from flask import jsonify, request, redirect, current_app
from flask.typing import ResponseReturnValue

from app.api.google import google_bp
from app.auth.guards import require_permission
from app.auth.identity import get_request_identity
from app.projects.store import DEFAULT_USER_ID
from app.providers.google.auth import google_auth_service
from app.workspaces.settings import workspace_settings_store
from app.workspaces.store import workspace_store


_GENERIC_OAUTH_ERROR = "Google authentication failed"


def _frontend_redirect(params: dict[str, str]) -> ResponseReturnValue:
    origin = str(current_app.config["FRONTEND_ORIGIN"]).rstrip("/")
    return redirect(f"{origin}?{urlencode(params)}")


def _oauth_success_redirect() -> ResponseReturnValue:
    return _frontend_redirect({"google_auth": "success"})


def _oauth_error_redirect(message: str = _GENERIC_OAUTH_ERROR) -> ResponseReturnValue:
    return _frontend_redirect({"google_auth": "error", "message": message})


def _get_current_user_id() -> str:
    """
    Get the current user ID from the authenticated session.

    Educational Note: In single-user mode (service key), this returns None
    which triggers the fallback to the default user in the database.
    For multi-user mode, implement JWT/session extraction here.

    Returns:
        User ID string from auth-required credentials, dev headers, or fallback
    """
    identity = get_request_identity()
    return identity.user_id


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


@google_bp.route('/google/status', methods=['GET'])
@require_permission("document_sources", "google_drive")
def google_status():
    """
    Check Google Drive configuration and connection status.

    Educational Note: This endpoint checks two things:
    1. Is Google OAuth configured? (workspace client ID + secret or env fallback)
    2. Is user connected? (valid tokens stored in Supabase users.google_tokens)

    Returns:
        {
            "success": true,
            "configured": true,   # OAuth credentials exist
            "connected": true,    # Valid tokens stored
            "email": "user@gmail.com"  # User's email if connected
        }
    """
    try:
        user_id = _get_current_user_id()
        workspace_id = _current_workspace_id()
        is_configured = google_auth_service.is_configured(workspace_id=workspace_id)
        is_connected, email = google_auth_service.is_connected(
            user_id=user_id,
            workspace_id=workspace_id,
        )

        return jsonify({
            'success': True,
            'configured': is_configured,
            'connected': is_connected,
            'email': email
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error checking Google status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@google_bp.route('/google/auth', methods=['GET'])
@require_permission("document_sources", "google_drive")
def google_auth():
    """
    Start Google OAuth flow by returning the authorization URL.

    Educational Note: The authorization URL contains:
    - client_id: Identifies our app to Google
    - redirect_uri: Where to send user after granting permission
    - scope: What permissions we're requesting (drive.readonly)
    - access_type=offline: Request a refresh token
    - prompt=consent: Always show consent screen (ensures refresh token)

    The frontend will redirect user to this URL.
    After user grants permission, Google redirects back to our callback.

    Returns:
        { "success": true, "auth_url": "https://accounts.google.com/..." }
    """
    try:
        workspace_id = _current_workspace_id()
        if not google_auth_service.is_configured(workspace_id=workspace_id):
            return jsonify({
                'success': False,
                'error': 'Google OAuth not configured. Please add Client ID and Secret in Workspace Settings.'
            }), 400

        user_id = _get_current_user_id()
        state = google_auth_service.build_state(
            user_id=user_id,
            secret_key=current_app.config["SECRET_KEY"],
            workspace_id=workspace_id,
        )
        auth_url = google_auth_service.get_auth_url(
            user_id=user_id,
            state=state,
            redirect_uri=current_app.config["GOOGLE_OAUTH_REDIRECT_URI"],
            workspace_id=workspace_id,
        )
        if not auth_url:
            return jsonify({
                'success': False,
                'error': 'Failed to generate auth URL'
            }), 500

        return jsonify({
            'success': True,
            'auth_url': auth_url
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error generating auth URL: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@google_bp.route('/google/callback', methods=['GET'])
def google_callback():
    """
    Handle OAuth callback from Google.

    Educational Note: This is where the OAuth "dance" completes:
    1. Google redirects here with ?code=AUTHORIZATION_CODE&state=SIGNED_STATE
    2. We exchange the code for access + refresh tokens
    3. Tokens are stored in Supabase users.google_tokens (per-user)
    4. We redirect user back to frontend with success/error

    Why redirect instead of JSON response?
    - This endpoint is called by Google's redirect, not our frontend
    - User's browser is at accounts.google.com when they click "Allow"
    - We need to send them back to our app with a visual confirmation

    Query Params:
        code: Authorization code from Google (on success)
        state: Signed one-time state token from get_auth_url
        error: Error message if user denied access

    Returns:
        Redirect to frontend with ?google_auth=success or ?google_auth=error
    """
    try:
        # Check for error (user denied access)
        error = request.args.get('error')
        if error:
            current_app.logger.warning("Google OAuth denied by provider: %s", error)
            return _oauth_error_redirect("Google authentication was cancelled")

        # Get authorization code
        code = request.args.get('code')
        if not code:
            current_app.logger.warning("Google OAuth callback missing authorization code")
            return _oauth_error_redirect()

        state = request.args.get('state', '')
        state_context = google_auth_service.parse_state_context(
            state=state,
            secret_key=current_app.config["SECRET_KEY"],
        )
        if not state_context:
            current_app.logger.warning("Google OAuth callback rejected invalid or replayed state")
            return _oauth_error_redirect()
        user_id = state_context["user_id"]

        # Exchange code for tokens, passing user_id for storage
        handle_kwargs = {
            "user_id": user_id,
            "redirect_uri": current_app.config["GOOGLE_OAUTH_REDIRECT_URI"],
        }
        if state_context.get("workspace_id"):
            handle_kwargs["workspace_id"] = state_context["workspace_id"]
        success, message = google_auth_service.handle_callback(
            code,
            **handle_kwargs,
        )

        if success:
            current_app.logger.info(f"Google OAuth successful: {message}")
            return _oauth_success_redirect()
        else:
            current_app.logger.error(f"Google OAuth failed: {message}")
            return _oauth_error_redirect()

    except Exception as e:
        current_app.logger.exception("Error in Google callback: %s", e)
        return _oauth_error_redirect()


@google_bp.route('/google/disconnect', methods=['POST'])
@require_permission("document_sources", "google_drive")
def google_disconnect():
    """
    Disconnect Google Drive by removing stored tokens.

    Educational Note: This removes tokens from Supabase users.google_tokens.
    User will need to re-authenticate to use Google Drive again.

    Note: This does NOT revoke access at Google's end - user can
    manually revoke at https://myaccount.google.com/permissions

    Returns:
        { "success": true, "message": "Disconnected successfully" }
    """
    try:
        user_id = _get_current_user_id()
        success, message = google_auth_service.disconnect(user_id=user_id)

        return jsonify({
            'success': success,
            'message': message
        }), 200 if success else 500

    except Exception as e:
        current_app.logger.error(f"Error disconnecting Google: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
