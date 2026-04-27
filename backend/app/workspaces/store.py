"""Workspace membership persistence, invites, and session context."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any, Dict, List, Optional

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer

from app.projects.store import DEFAULT_USER_ID
from app.providers.supabase import get_supabase, is_supabase_enabled

logger = logging.getLogger(__name__)

INVITE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
INVITE_TOKEN_SALT = "noobbook.workspace-invite"


WORKSPACE_OWNER = "owner"
WORKSPACE_ADMIN = "admin"
WORKSPACE_MEMBER = "member"
MANAGE_WORKSPACE_ROLES = {WORKSPACE_OWNER, WORKSPACE_ADMIN}
WORKSPACE_ROLES = {WORKSPACE_OWNER, WORKSPACE_ADMIN, WORKSPACE_MEMBER}

PROJECT_OWNER = "owner"
PROJECT_EDITOR = "editor"
PROJECT_VIEWER = "viewer"
PROJECT_ROLES = {PROJECT_OWNER, PROJECT_EDITOR, PROJECT_VIEWER}


def _personal_workspace_name(email: Optional[str]) -> str:
    local = (email or "").split("@", 1)[0].strip()
    return f"{local or 'Personal'}'s Workspace"


def _synthetic_workspace(user_id: str, email: Optional[str]) -> Dict[str, Any]:
    workspace = {
        "id": DEFAULT_USER_ID,
        "name": _personal_workspace_name(email),
        "role": WORKSPACE_OWNER,
        "owner_user_id": user_id,
        "is_personal": True,
    }
    return {
        "available_workspaces": [workspace],
        "selected_workspace": workspace,
        "selected_workspace_id": workspace["id"],
        "workspace_role": WORKSPACE_OWNER,
        "can_manage_workspace": True,
        "can_create_project": True,
    }


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret_key, salt=INVITE_TOKEN_SALT)


class WorkspaceStore:
    """Own workspace/team membership data access."""

    def __init__(self) -> None:
        self.supabase = get_supabase() if is_supabase_enabled() else None

    def ensure_personal_workspace(self, user_id: str, email: Optional[str]) -> Dict[str, Any]:
        """Create or return the user's personal workspace and owner membership."""
        if not self.supabase:
            return _synthetic_workspace(user_id, email)["selected_workspace"]

        existing = (
            self.supabase.table("workspaces")
            .select("id, name, owner_user_id, personal_owner_user_id")
            .eq("personal_owner_user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            workspace = existing.data[0]
        else:
            inserted = (
                self.supabase.table("workspaces")
                .insert({
                    "name": _personal_workspace_name(email),
                    "owner_user_id": user_id,
                    "personal_owner_user_id": user_id,
                    "settings": {},
                })
                .execute()
            )
            if not inserted.data:
                raise RuntimeError("Failed to create personal workspace")
            workspace = inserted.data[0]

        self.supabase.table("workspace_members").upsert(
            {
                "workspace_id": workspace["id"],
                "user_id": user_id,
                "role": WORKSPACE_OWNER,
            },
            on_conflict="workspace_id,user_id",
        ).execute()
        return self._workspace_summary(workspace, WORKSPACE_OWNER)

    def create_workspace(self, name: str, owner_user_id: str) -> Dict[str, Any]:
        """Create a workspace and make the caller its owner."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Workspace name is required")
        if not self.supabase:
            workspace = {
                "id": DEFAULT_USER_ID,
                "name": clean_name,
                "owner_user_id": owner_user_id,
                "personal_owner_user_id": None,
            }
            return self._workspace_summary(workspace, WORKSPACE_OWNER)

        inserted = (
            self.supabase.table("workspaces")
            .insert({
                "name": clean_name,
                "owner_user_id": owner_user_id,
                "settings": {},
            })
            .execute()
        )
        if not inserted.data:
            raise RuntimeError("Failed to create workspace")
        workspace = inserted.data[0]
        self.supabase.table("workspace_members").upsert(
            {
                "workspace_id": workspace["id"],
                "user_id": owner_user_id,
                "role": WORKSPACE_OWNER,
            },
            on_conflict="workspace_id,user_id",
        ).execute()
        return self._workspace_summary(workspace, WORKSPACE_OWNER)

    def session_context(
        self,
        user_id: str,
        email: Optional[str],
        selected_workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return available workspaces plus selected workspace capabilities."""
        if not self.supabase:
            return _synthetic_workspace(user_id, email)

        try:
            memberships = self._list_memberships(user_id)
            if not memberships:
                self.ensure_personal_workspace(user_id, email)
                memberships = self._list_memberships(user_id)

            workspace_ids = [row["workspace_id"] for row in memberships if row.get("workspace_id")]
            workspaces = self._list_workspaces(workspace_ids)
            role_by_workspace = {
                row["workspace_id"]: row.get("role") or WORKSPACE_MEMBER
                for row in memberships
                if row.get("workspace_id")
            }

            summaries = [
                self._workspace_summary(workspace, role_by_workspace.get(workspace["id"], WORKSPACE_MEMBER))
                for workspace in workspaces
            ]
            selected = self._select_workspace(summaries, selected_workspace_id)
            role = selected.get("role") if selected else None
            return {
                "available_workspaces": summaries,
                "selected_workspace": selected,
                "selected_workspace_id": selected.get("id") if selected else None,
                "workspace_role": role,
                "can_manage_workspace": role in MANAGE_WORKSPACE_ROLES,
                "can_create_project": selected is not None,
            }
        except Exception as exc:
            logger.warning("Failed to load workspace session context: %s", exc)
            return _synthetic_workspace(user_id, email)

    def list_members(self, workspace_id: str, requester_user_id: str) -> List[Dict[str, Any]]:
        """List members for a workspace visible to the requester."""
        if not self.supabase:
            return [{
                "user_id": requester_user_id,
                "email": None,
                "role": WORKSPACE_OWNER,
                "created_at": None,
                "updated_at": None,
            }]
        if not self.has_workspace_access(workspace_id, requester_user_id):
            raise PermissionError("Workspace access required")

        response = (
            self.supabase.table("workspace_members")
            .select("user_id, role, created_at, updated_at")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        rows = response.data or []
        emails = self._emails_by_user_id([str(row["user_id"]) for row in rows if row.get("user_id")])
        return [
            {
                "user_id": str(row["user_id"]),
                "email": emails.get(str(row["user_id"])),
                "role": row.get("role") or WORKSPACE_MEMBER,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ]

    def has_workspace_access(self, workspace_id: str, user_id: str) -> bool:
        if not workspace_id or not user_id:
            return False
        if not self.supabase:
            return True
        response = (
            self.supabase.table("workspace_members")
            .select("id")
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def can_manage_workspace(self, workspace_id: str, user_id: str) -> bool:
        if not workspace_id or not user_id:
            return False
        if not self.supabase:
            return True
        role = self._workspace_role_for_user(workspace_id, user_id)
        return role in MANAGE_WORKSPACE_ROLES

    def _workspace_role_for_user(self, workspace_id: str, user_id: str) -> Optional[str]:
        response = (
            self.supabase.table("workspace_members")
            .select("role")
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        role = response.data[0].get("role")
        return str(role) if role else None

    def create_invite(
        self,
        *,
        workspace_id: str,
        email: str,
        invited_by_user_id: str,
        secret_key: str,
        workspace_role: str = WORKSPACE_MEMBER,
        project_id: Optional[str] = None,
        project_role: Optional[str] = None,
        max_age_seconds: int = INVITE_MAX_AGE_SECONDS,
        require_workspace_manager: bool = True,
    ) -> Dict[str, Any]:
        """Create a signed one-time workspace invite."""
        clean_email = _normalize_email(email)
        if not clean_email:
            raise ValueError("email is required")
        if workspace_role not in WORKSPACE_ROLES:
            raise ValueError("workspace_role must be owner, admin, or member")
        if project_id:
            if project_role not in PROJECT_ROLES:
                raise ValueError("project_role must be owner, editor, or viewer")
        elif project_role:
            raise ValueError("project_role requires project_id")
        requester_role = WORKSPACE_OWNER
        if self.supabase:
            requester_role = self._workspace_role_for_user(workspace_id, invited_by_user_id) or ""
        if require_workspace_manager and requester_role not in MANAGE_WORKSPACE_ROLES:
            raise PermissionError("Workspace owner or admin role required")
        if workspace_role == WORKSPACE_OWNER and requester_role != WORKSPACE_OWNER:
            raise PermissionError("Workspace owner role required")
        if not require_workspace_manager and workspace_role != WORKSPACE_MEMBER:
            raise PermissionError("Project invites can only grant workspace member role")

        nonce = token_urlsafe(24)
        token = _serializer(secret_key).dumps({
            "workspace_id": workspace_id,
            "email": clean_email,
            "nonce": nonce,
        })
        expires_at = _utc_now() + timedelta(seconds=max_age_seconds)

        invite = {
            "workspace_id": workspace_id,
            "email": clean_email,
            "workspace_role": workspace_role,
            "project_id": project_id,
            "project_role": project_role,
            "token_hash": _hash_token(token),
            "invited_by_user_id": invited_by_user_id,
            "expires_at": expires_at.isoformat(),
        }
        if not self.supabase:
            return self._format_invite({**invite, "id": nonce}, token)

        response = self.supabase.table("workspace_invites").insert(invite).execute()
        if not response.data:
            raise RuntimeError("Failed to create workspace invite")
        return self._format_invite(response.data[0], token)

    def accept_invite(
        self,
        *,
        token: str,
        user_id: str,
        user_email: Optional[str],
        secret_key: str,
    ) -> Dict[str, Any]:
        """Accept a signed one-time invite for the authenticated user."""
        clean_email = _normalize_email(user_email or "")
        if not clean_email:
            raise PermissionError("Authenticated user email required")
        try:
            payload = _serializer(secret_key).loads(
                token,
                max_age=INVITE_MAX_AGE_SECONDS,
            )
        except (BadData, SignatureExpired):
            raise ValueError("Invalid or expired invite") from None
        if not isinstance(payload, dict):
            raise ValueError("Invalid or expired invite")
        invited_email = _normalize_email(str(payload.get("email") or ""))
        if invited_email != clean_email:
            raise PermissionError("Invite email does not match authenticated user")

        if not self.supabase:
            workspace = _synthetic_workspace(user_id, clean_email)["selected_workspace"]
            return {
                "workspace": workspace,
                "workspace_role": WORKSPACE_MEMBER,
                "project_id": None,
                "project_role": None,
            }

        now = _utc_now().isoformat()
        response = (
            self.supabase.table("workspace_invites")
            .update({"accepted_at": now})
            .eq("token_hash", _hash_token(token))
            .is_("accepted_at", "null")
            .is_("revoked_at", "null")
            .gt("expires_at", now)
            .execute()
        )
        if not response.data:
            raise ValueError("Invalid or expired invite")
        invite = response.data[0]

        self.supabase.table("workspace_members").upsert(
            {
                "workspace_id": invite["workspace_id"],
                "user_id": user_id,
                "role": invite.get("workspace_role") or WORKSPACE_MEMBER,
            },
            on_conflict="workspace_id,user_id",
        ).execute()
        if invite.get("project_id") and invite.get("project_role"):
            self.supabase.table("project_members").upsert(
                {
                    "project_id": invite["project_id"],
                    "user_id": user_id,
                    "role": invite["project_role"],
                },
                on_conflict="project_id,user_id",
            ).execute()

        workspace = self._get_workspace_summary(
            invite["workspace_id"],
            invite.get("workspace_role") or WORKSPACE_MEMBER,
        )
        return {
            "workspace": workspace,
            "workspace_role": invite.get("workspace_role") or WORKSPACE_MEMBER,
            "project_id": invite.get("project_id"),
            "project_role": invite.get("project_role"),
        }

    def _list_memberships(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.supabase.table("workspace_members")
            .select("workspace_id, role")
            .eq("user_id", user_id)
            .execute()
        )
        return response.data or []

    def _get_workspace_summary(self, workspace_id: str, role: str) -> Dict[str, Any]:
        response = (
            self.supabase.table("workspaces")
            .select("id, name, owner_user_id, personal_owner_user_id")
            .eq("id", workspace_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise ValueError("Workspace not found")
        return self._workspace_summary(response.data[0], role)

    def _list_workspaces(self, workspace_ids: List[str]) -> List[Dict[str, Any]]:
        if not workspace_ids:
            return []
        response = (
            self.supabase.table("workspaces")
            .select("id, name, owner_user_id, personal_owner_user_id")
            .in_("id", workspace_ids)
            .execute()
        )
        return response.data or []

    @staticmethod
    def _workspace_summary(workspace: Dict[str, Any], role: str) -> Dict[str, Any]:
        return {
            "id": str(workspace["id"]),
            "name": workspace.get("name") or "Workspace",
            "role": role,
            "owner_user_id": str(workspace["owner_user_id"]) if workspace.get("owner_user_id") else None,
            "is_personal": bool(workspace.get("personal_owner_user_id")),
        }

    @staticmethod
    def _select_workspace(
        workspaces: List[Dict[str, Any]],
        selected_workspace_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not workspaces:
            return None
        if selected_workspace_id:
            for workspace in workspaces:
                if workspace["id"] == selected_workspace_id:
                    return workspace
        for workspace in workspaces:
            if workspace.get("is_personal"):
                return workspace
        return workspaces[0]

    def _emails_by_user_id(self, user_ids: List[str]) -> Dict[str, Optional[str]]:
        if not user_ids or not self.supabase:
            return {}
        response = (
            self.supabase.table("users")
            .select("id, email")
            .in_("id", user_ids)
            .execute()
        )
        return {
            str(row["id"]): row.get("email")
            for row in response.data or []
            if row.get("id")
        }

    @staticmethod
    def _format_invite(invite: Dict[str, Any], token: str) -> Dict[str, Any]:
        return {
            "id": str(invite["id"]),
            "workspace_id": str(invite["workspace_id"]),
            "email": invite["email"],
            "workspace_role": invite.get("workspace_role") or WORKSPACE_MEMBER,
            "project_id": str(invite["project_id"]) if invite.get("project_id") else None,
            "project_role": invite.get("project_role"),
            "expires_at": invite.get("expires_at"),
            "token": token,
        }


workspace_store = WorkspaceStore()
