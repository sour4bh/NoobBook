from unittest.mock import patch

import pytest

from app.workspaces.store import WorkspaceStore


PROJECT_ID = "00000000-0000-0000-0000-000000000000"


def test_workspace_invite_token_acceptance_is_signed_and_email_bound() -> None:
    store = WorkspaceStore.__new__(WorkspaceStore)
    store.supabase = None

    invite = store.create_invite(
        workspace_id="workspace-1",
        email="Invitee@Example.com",
        workspace_role="member",
        invited_by_user_id="owner-1",
        secret_key="test-secret",
    )

    accepted = store.accept_invite(
        token=invite["token"],
        user_id="invitee-1",
        user_email="invitee@example.com",
        secret_key="test-secret",
    )

    assert accepted["workspace_role"] == "member"
    with pytest.raises(PermissionError):
        store.accept_invite(
            token=invite["token"],
            user_id="other-1",
            user_email="other@example.com",
            secret_key="test-secret",
        )
    with pytest.raises(ValueError):
        store.accept_invite(
            token=f"{invite['token']}tampered",
            user_id="invitee-1",
            user_email="invitee@example.com",
            secret_key="test-secret",
        )


def test_workspace_invite_route_creates_signed_invite(auth_client, auth_optional_env):
    invite = {
        "id": "invite-1",
        "workspace_id": "workspace-1",
        "email": "new@example.com",
        "workspace_role": "member",
        "project_id": None,
        "project_role": None,
        "expires_at": "2026-01-01T00:00:00+00:00",
        "token": "signed-token",
    }
    with patch("app.api.workspaces.routes.workspace_store") as store:
        store.create_invite.return_value = invite

        response = auth_client.post(
            "/api/v1/workspaces/workspace-1/invites",
            json={"email": "new@example.com", "workspace_role": "member"},
        )

    assert response.status_code == 201
    assert response.get_json()["invite"] == invite
    store.create_invite.assert_called_once()
    assert store.create_invite.call_args.kwargs["workspace_id"] == "workspace-1"
    assert store.create_invite.call_args.kwargs["email"] == "new@example.com"


def test_project_member_route_adds_existing_workspace_member(
    auth_client,
    auth_optional_env,
):
    member = {"user_id": "member-1", "role": "editor", "email": "m@example.com"}
    with patch("app.api.projects.members.project_service") as projects:
        projects.add_project_member.return_value = member

        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/members",
            json={"user_id": "member-1", "role": "editor"},
        )

    assert response.status_code == 201
    assert response.get_json()["member"] == member
    projects.add_project_member.assert_called_once_with(
        project_id=PROJECT_ID,
        target_user_id="member-1",
        role="editor",
        requester_user_id="00000000-0000-0000-0000-000000000001",
    )


def test_project_invite_requires_project_owner(auth_client, auth_optional_env):
    with patch("app.api.projects.members.project_service") as projects, patch(
        "app.api.projects.members.workspace_store"
    ) as workspaces:
        projects.can_manage_project.return_value = False

        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/invites",
            json={"email": "new@example.com"},
        )

    assert response.status_code == 403
    assert response.get_json() == {
        "success": False,
        "error": "Project owner role required",
    }
    workspaces.create_invite.assert_not_called()


def test_project_invite_creates_workspace_invite_with_project_role(
    auth_client,
    auth_optional_env,
):
    project = {"id": PROJECT_ID, "workspace_id": "workspace-1"}
    invite = {
        "id": "invite-1",
        "workspace_id": "workspace-1",
        "email": "new@example.com",
        "workspace_role": "member",
        "project_id": PROJECT_ID,
        "project_role": "viewer",
        "expires_at": "2026-01-01T00:00:00+00:00",
        "token": "signed-token",
    }
    with patch("app.api.projects.members.project_service") as projects, patch(
        "app.api.projects.members.workspace_store"
    ) as workspaces:
        projects.can_manage_project.return_value = True
        projects.get_project.return_value = project
        workspaces.create_invite.return_value = invite

        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/invites",
            json={"email": "new@example.com", "project_role": "viewer"},
        )

    assert response.status_code == 201
    assert response.get_json()["invite"] == invite
    workspaces.create_invite.assert_called_once()
    assert workspaces.create_invite.call_args.kwargs["workspace_id"] == "workspace-1"
    assert workspaces.create_invite.call_args.kwargs["project_id"] == PROJECT_ID
    assert workspaces.create_invite.call_args.kwargs["project_role"] == "viewer"
    assert workspaces.create_invite.call_args.kwargs["require_workspace_manager"] is False


def test_project_invite_cannot_grant_workspace_admin(auth_client, auth_optional_env):
    project = {"id": PROJECT_ID, "workspace_id": "workspace-1"}
    with patch("app.api.projects.members.project_service") as projects, patch(
        "app.api.projects.members.workspace_store"
    ) as workspaces:
        projects.can_manage_project.return_value = True
        projects.get_project.return_value = project

        response = auth_client.post(
            f"/api/v1/projects/{PROJECT_ID}/invites",
            json={"email": "new@example.com", "workspace_role": "admin"},
        )

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": "Project invites can only grant workspace member role",
    }
    workspaces.create_invite.assert_not_called()
