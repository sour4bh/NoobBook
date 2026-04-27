"""Project sharing and private-project membership routes."""

from flask import current_app, jsonify, request

from app.api.projects import projects_bp
from app.auth.identity import get_request_identity
from app.projects.store import project_service
from app.workspaces.store import workspace_store


def _secret_key() -> str:
    return str(current_app.config["SECRET_KEY"])


@projects_bp.route("/projects/<project_id>/members", methods=["GET"])
def list_project_members(project_id: str):
    """List private-project members."""
    try:
        identity = get_request_identity()
        members = project_service.list_project_members(project_id, identity.user_id)
        return jsonify({"success": True, "members": members, "count": len(members)}), 200
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error listing project members: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@projects_bp.route("/projects/<project_id>/members", methods=["POST"])
def add_project_member(project_id: str):
    """Add an existing workspace member to a private project."""
    try:
        identity = get_request_identity()
        data = request.get_json() or {}
        user_id = (data.get("user_id") or "").strip()
        role = (data.get("role") or "viewer").strip().lower()
        if not user_id:
            return jsonify({"success": False, "error": "user_id is required"}), 400
        member = project_service.add_project_member(
            project_id=project_id,
            target_user_id=user_id,
            role=role,
            requester_user_id=identity.user_id,
        )
        return jsonify({"success": True, "member": member}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error adding project member: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@projects_bp.route("/projects/<project_id>/members/<member_user_id>", methods=["PUT"])
def update_project_member(project_id: str, member_user_id: str):
    """Update a private-project member role."""
    try:
        identity = get_request_identity()
        data = request.get_json() or {}
        role = (data.get("role") or "").strip().lower()
        member = project_service.update_project_member_role(
            project_id=project_id,
            target_user_id=member_user_id,
            role=role,
            requester_user_id=identity.user_id,
        )
        return jsonify({"success": True, "member": member}), 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error updating project member: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@projects_bp.route("/projects/<project_id>/members/<member_user_id>", methods=["DELETE"])
def remove_project_member(project_id: str, member_user_id: str):
    """Remove a private-project member."""
    try:
        identity = get_request_identity()
        removed = project_service.remove_project_member(
            project_id=project_id,
            target_user_id=member_user_id,
            requester_user_id=identity.user_id,
        )
        if not removed:
            return jsonify({"success": False, "error": "Project member not found"}), 404
        return jsonify({"success": True}), 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error removing project member: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@projects_bp.route("/projects/<project_id>/invites", methods=["POST"])
def create_project_invite(project_id: str):
    """Create a signed workspace invite that also grants project access."""
    try:
        identity = get_request_identity()
        if not project_service.can_manage_project(project_id, identity.user_id):
            return jsonify({"success": False, "error": "Project owner role required"}), 403
        project = project_service.get_project(project_id, user_id=identity.user_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404

        data = request.get_json() or {}
        workspace_role = (data.get("workspace_role") or "member").strip().lower()
        if workspace_role != "member":
            return jsonify({
                "success": False,
                "error": "Project invites can only grant workspace member role",
            }), 400
        invite = workspace_store.create_invite(
            workspace_id=project["workspace_id"],
            email=(data.get("email") or ""),
            workspace_role="member",
            project_id=project_id,
            project_role=(data.get("project_role") or "viewer"),
            invited_by_user_id=identity.user_id,
            secret_key=_secret_key(),
            require_workspace_manager=False,
        )
        return jsonify({"success": True, "invite": invite}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except Exception as exc:
        current_app.logger.error("Error creating project invite: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500
