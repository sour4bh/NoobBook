"""Workspace membership persistence and session context."""

import logging
from typing import Any, Dict, List, Optional

from app.projects.store import DEFAULT_USER_ID
from app.providers.supabase import get_supabase, is_supabase_enabled

logger = logging.getLogger(__name__)


WORKSPACE_OWNER = "owner"
WORKSPACE_ADMIN = "admin"
WORKSPACE_MEMBER = "member"
MANAGE_WORKSPACE_ROLES = {WORKSPACE_OWNER, WORKSPACE_ADMIN}


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

    def _list_memberships(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.supabase.table("workspace_members")
            .select("workspace_id, role")
            .eq("user_id", user_id)
            .execute()
        )
        return response.data or []

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


workspace_store = WorkspaceStore()
