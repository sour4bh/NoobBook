"""Workspace membership and invite transport routes."""

from flask import current_app, jsonify, request

from app.api.workspaces import workspaces_bp
from app.auth.identity import get_request_identity
from app.workspaces.store import workspace_store


def _secret_key() -> str:
    return str(current_app.config["SECRET_KEY"])


@workspaces_bp.route("/workspaces", methods=["GET"])
def list_workspaces():
    """Return the current user's workspace session context."""
    identity = get_request_identity()
    return jsonify({
        "success": True,
        "workspace": workspace_store.session_context(
            user_id=identity.user_id,
            email=identity.email,
            selected_workspace_id=request.args.get("workspace_id"),
        ),
    }), 200


@workspaces_bp.route("/workspaces", methods=["POST"])
def create_workspace():
    """Create a new workspace owned by the current user."""
    try:
        identity = get_request_identity()
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        workspace = workspace_store.create_workspace(name, identity.user_id)
        return jsonify({"success": True, "workspace": workspace}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.error("Error creating workspace: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@workspaces_bp.route("/workspaces/<workspace_id>/members", methods=["GET"])
def list_workspace_members(workspace_id: str):
    """List workspace members visible to workspace members."""
    try:
        identity = get_request_identity()
        members = workspace_store.list_members(workspace_id, identity.user_id)
        return jsonify({"success": True, "members": members, "count": len(members)}), 200
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error listing workspace members: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@workspaces_bp.route("/workspaces/<workspace_id>/invites", methods=["POST"])
def create_workspace_invite(workspace_id: str):
    """Create a signed one-time workspace invite."""
    try:
        identity = get_request_identity()
        data = request.get_json() or {}
        invite = workspace_store.create_invite(
            workspace_id=workspace_id,
            email=(data.get("email") or ""),
            workspace_role=(data.get("workspace_role") or "member"),
            invited_by_user_id=identity.user_id,
            secret_key=_secret_key(),
        )
        return jsonify({"success": True, "invite": invite}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error creating workspace invite: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@workspaces_bp.route("/workspace-invites/<path:token>/accept", methods=["POST"])
def accept_workspace_invite(token: str):
    """Accept a signed one-time workspace invite as the current user."""
    try:
        identity = get_request_identity()
        accepted = workspace_store.accept_invite(
            token=token,
            user_id=identity.user_id,
            user_email=identity.email,
            secret_key=_secret_key(),
        )
        return jsonify({"success": True, **accepted}), 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error accepting workspace invite: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500
