"""
Project Service - Business logic for project management.

Educational Note: This service layer handles all project-related operations
using Supabase as the database backend. It provides a clean abstraction
over database operations.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any

from app.providers.supabase import get_supabase, is_supabase_enabled

logger = logging.getLogger(__name__)

PROJECT_OWNER = "owner"
PROJECT_EDITOR = "editor"
PROJECT_VIEWER = "viewer"
PROJECT_EDIT_ROLES = {PROJECT_OWNER, PROJECT_EDITOR}
PROJECT_ROLES = {PROJECT_OWNER, PROJECT_EDITOR, PROJECT_VIEWER}


# Default user ID for single-user mode (fallback when no auth token provided).
# Policy decision about when DEFAULT_USER_ID applies lives in
# `app.auth.identity.get_request_identity` — that resolver owns the
# `NOOBBOOK_AUTH_REQUIRED` gate. Code here is a CRUD convenience so call
# sites do not have to check for `user_id is None`; it must never be used
# to decide whether a caller is authenticated. NBB-705A will audit
# remaining data-service default-user fallbacks.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _resolve_user_id(user_id: Optional[str] = None) -> str:
    """Return `user_id` or `DEFAULT_USER_ID` for single-user convenience.

    Policy lives in `app.auth.identity`; this helper only hides a
    `None`-check from the Supabase CRUD call sites below.
    """
    return user_id or DEFAULT_USER_ID


class ProjectStore:
    """
    Service class for managing projects using Supabase.

    Educational Note: This service uses Supabase's PostgREST API for
    database operations. Each method maps to SQL queries under the hood.
    """

    def __init__(self):
        """Initialize the project service."""
        if not is_supabase_enabled():
            raise RuntimeError(
                "Supabase is not configured. Please add SUPABASE_URL and "
                "SUPABASE_ANON_KEY to your .env file."
            )
        self.supabase = get_supabase()
        self.table = "projects"

    def list_all_projects(
        self,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all available projects for the given user.

        Args:
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            List of project metadata sorted by last_accessed (most recent first)

        Educational Note: Supabase's select() returns a response object.
        We access .data to get the actual records.
        """
        uid = _resolve_user_id(user_id)
        if not workspace_id:
            raise ValueError("workspace_id is required")

        memberships = (
            self.supabase.table("project_members")
            .select("project_id")
            .eq("user_id", uid)
            .execute()
        )
        project_ids = [
            row["project_id"]
            for row in (memberships.data or [])
            if row.get("project_id")
        ]
        if not project_ids:
            return []

        response = (
            self.supabase.table(self.table)
            .select("id, workspace_id, name, description, created_at, updated_at, last_accessed, costs")
            .eq("workspace_id", workspace_id)
            .in_("id", project_ids)
            .order("last_accessed", desc=True)
            .execute()
        )
        return response.data or []

    def create_project(
        self,
        name: str,
        description: str = "",
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new project.

        Args:
            name: Project name
            description: Optional project description
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Created project object

        Raises:
            ValueError: If project name already exists

        Educational Note: Supabase's insert() returns the inserted row(s).
        We use .select() after insert to get the full record back.
        """
        uid = _resolve_user_id(user_id)
        if not workspace_id:
            raise ValueError("workspace_id is required")
        if not self.has_workspace_access(workspace_id, uid):
            raise PermissionError("Workspace access required")

        # Project names are unique within the workspace.
        existing = (
            self.supabase.table(self.table)
            .select("id")
            .eq("workspace_id", workspace_id)
            .ilike("name", name)
            .execute()
        )

        if existing.data:
            raise ValueError(f"Project with name '{name}' already exists")

        # Create project data
        project_data = {
            "user_id": uid,
            "workspace_id": workspace_id,
            "name": name,
            "description": description,
            "custom_prompt": None,
            "memory": {},
            "costs": {"total_cost": 0.0, "by_model": {}}
        }

        # Insert and return the new project
        response = (
            self.supabase.table(self.table)
            .insert(project_data)
            .execute()
        )

        if response.data:
            project = response.data[0]
            self.supabase.table("project_members").upsert(
                {
                    "project_id": project["id"],
                    "user_id": uid,
                    "role": PROJECT_OWNER,
                },
                on_conflict="project_id,user_id",
            ).execute()
            return self._format_project_metadata(project)

        raise RuntimeError("Failed to create project")

    def get_project(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get full project data by ID.

        Args:
            project_id: The project UUID
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Full project data or None if not found

        Educational Note: Reads are side-effect free. The dedicated
        open_project() method records last_accessed when the user opens a
        project from the dashboard.
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid and not self.has_project_access(project_id, uid):
            return None

        response = (
            self.supabase.table(self.table)
            .select("*")
            .eq("id", project_id)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update project metadata.

        Args:
            project_id: The project UUID
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated project metadata or None if not found

        Raises:
            ValueError: If new name conflicts with existing project
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid:
            role = self.get_project_role(project_id, uid)
            if role is None:
                return None
            if role not in PROJECT_EDIT_ROLES:
                raise PermissionError("Project editor role required")

        # Check if project exists
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        # Check if new name conflicts with existing project for this user
        if name and name != project["name"]:
            existing = (
                self.supabase.table(self.table)
                .select("id")
                .eq("workspace_id", project.get("workspace_id"))
                .ilike("name", name)
                .neq("id", project_id)
                .execute()
            )
            if existing.data:
                raise ValueError(f"Project with name '{name}' already exists")

        # Build update data
        update_data = {}
        if name:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description

        if not update_data:
            return self._format_project_metadata(project)

        # Update project
        response = (
            self.supabase.table(self.table)
            .update(update_data)
            .eq("id", project_id)
            .execute()
        )

        if response.data:
            return self._format_project_metadata(response.data[0])

        return None

    def delete_project(self, project_id: str, user_id: Optional[str] = None) -> bool:
        """
        Delete a project.

        Args:
            project_id: The project UUID
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            True if deleted, False if not found

        Educational Note: Supabase cascades deletes automatically based on
        foreign key constraints. Deleting a project also deletes its
        sources, chats, messages, etc.
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid:
            role = self.get_project_role(project_id, uid)
            if role is None:
                return False
            if role != PROJECT_OWNER:
                raise PermissionError("Project owner role required")

        # Check if project exists first
        existing = (
            self.supabase.table(self.table)
            .select("id")
            .eq("id", project_id)
            .execute()
        )

        if not existing.data:
            return False

        # Delete the project
        self.supabase.table(self.table).delete().eq("id", project_id).execute()

        return True

    def open_project(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Open a project (update last accessed time).

        Args:
            project_id: The project UUID
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Project metadata or None if not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        project = self.get_project(project_id, user_id=uid)
        if not project:
            return None

        last_accessed = datetime.now().isoformat()
        response = (
            self.supabase.table(self.table)
            .update({"last_accessed": last_accessed})
            .eq("id", project_id)
            .execute()
        )

        if response.data:
            return self._format_project_metadata(response.data[0])

        project["last_accessed"] = last_accessed
        return self._format_project_metadata(project)

    def update_custom_prompt(
        self,
        project_id: str,
        custom_prompt: Optional[str],
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update the project's custom system prompt.

        Args:
            project_id: The project UUID
            custom_prompt: The custom prompt string, or None to reset to default
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Updated project or None if project not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid:
            role = self.get_project_role(project_id, uid)
            if role is None:
                return None
            if role not in PROJECT_EDIT_ROLES:
                raise PermissionError("Project editor role required")

        # Check if project exists
        existing = (
            self.supabase.table(self.table)
            .select("id")
            .eq("id", project_id)
            .execute()
        )

        if not existing.data:
            return None

        # Update custom prompt
        response = (
            self.supabase.table(self.table)
            .update({"custom_prompt": custom_prompt})
            .eq("id", project_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def get_project_settings(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get the project's settings.

        Args:
            project_id: The project UUID
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Project settings or None if project not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid and not self.has_project_access(project_id, uid):
            return None

        response = (
            self.supabase.table(self.table)
            .select("custom_prompt, memory")
            .eq("id", project_id)
            .execute()
        )

        if not response.data:
            return None

        project = response.data[0]

        # Return settings with defaults
        return {
            "ai_model": "claude-sonnet-4-6",
            "auto_save": True,
            "custom_prompt": project.get("custom_prompt")
        }

    def get_project_costs(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get the project's API usage costs.

        Args:
            project_id: The project UUID
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Project costs or None if project not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid and not self.has_project_access(project_id, uid):
            return None

        response = (
            self.supabase.table(self.table)
            .select("costs")
            .eq("id", project_id)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0].get("costs", {"total_cost": 0.0, "by_model": {}})

    def update_project_costs(
        self,
        project_id: str,
        costs: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Update the project's API usage costs.

        Args:
            project_id: The project UUID
            costs: Updated costs dictionary

        Returns:
            True if updated, False if project not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid:
            role = self.get_project_role(project_id, uid)
            if role is None:
                return False
            if role not in PROJECT_EDIT_ROLES:
                raise PermissionError("Project editor role required")

        response = (
            self.supabase.table(self.table)
            .update({"costs": costs})
            .eq("id", project_id)
            .execute()
        )

        return bool(response.data)

    def get_project_memory(self, project_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get the project's memory.

        Args:
            project_id: The project UUID
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            Project memory or None if project not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid and not self.has_project_access(project_id, uid):
            return None

        response = (
            self.supabase.table(self.table)
            .select("memory")
            .eq("id", project_id)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0].get("memory", {})

    def update_project_memory(
        self,
        project_id: str,
        memory: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Update the project's memory.

        Args:
            project_id: The project UUID
            memory: Updated memory dictionary

        Returns:
            True if updated, False if project not found
        """
        uid = _resolve_user_id(user_id) if user_id is not None else None
        if uid:
            role = self.get_project_role(project_id, uid)
            if role is None:
                return False
            if role not in PROJECT_EDIT_ROLES:
                raise PermissionError("Project editor role required")

        response = (
            self.supabase.table(self.table)
            .update({"memory": memory})
            .eq("id", project_id)
            .execute()
        )

        return bool(response.data)

    # ==================== User Memory Methods ====================

    def get_user_memory(self, user_id: Optional[str] = None) -> Optional[str]:
        """
        Get the user's global memory.

        Educational Note: User memory persists across all projects
        and stores global preferences like name, communication style, etc.

        Args:
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            User memory string or None if not found
        """
        uid = _resolve_user_id(user_id)
        response = (
            self.supabase.table("users")
            .select("memory")
            .eq("id", uid)
            .execute()
        )

        if not response.data:
            return None

        memory_data = response.data[0].get("memory", {})
        return memory_data.get("memory") if memory_data else None

    def update_user_memory(self, memory: str, user_id: Optional[str] = None) -> bool:
        """
        Update the user's global memory.

        Args:
            memory: The memory content string
            user_id: The user's UUID (falls back to DEFAULT_USER_ID)

        Returns:
            True if updated successfully
        """
        from datetime import datetime

        uid = _resolve_user_id(user_id)
        memory_data = {
            "memory": memory,
            "updated_at": datetime.now().isoformat()
        }

        response = (
            self.supabase.table("users")
            .update({"memory": memory_data})
            .eq("id", uid)
            .execute()
        )

        return bool(response.data)

    def _format_project_metadata(self, project: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format project data to return only metadata fields.

        Educational Note: This helper ensures consistent response format
        and excludes large fields like memory and full settings.
        """
        return {
            "id": project["id"],
            "workspace_id": project.get("workspace_id"),
            "name": project["name"],
            "description": project.get("description", ""),
            "created_at": project["created_at"],
            "updated_at": project["updated_at"],
            "last_accessed": project.get("last_accessed", project["updated_at"]),
            "costs": project.get("costs", {})
        }

    def get_project_owner_id(self, project_id: str) -> Optional[str]:
        """Get the owning user_id for a project (internal use)."""
        response = (
            self.supabase.table(self.table)
            .select("user_id")
            .eq("id", project_id)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0].get("user_id")

    def has_workspace_access(self, workspace_id: str, user_id: str) -> bool:
        """Check if a user is a workspace member."""
        if not workspace_id or not user_id:
            return False
        response = (
            self.supabase.table("workspace_members")
            .select("id")
            .eq("workspace_id", workspace_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(response.data)

    def get_project_role(self, project_id: str, user_id: str) -> Optional[str]:
        """Return a user's explicit private-project role."""
        if not project_id or not user_id:
            return None
        response = (
            self.supabase.table("project_members")
            .select("role")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        role = response.data[0].get("role")
        return str(role) if role else None

    def has_project_access(self, project_id: str, user_id: str) -> bool:
        """Check if a user has explicit private-project membership."""
        return self.get_project_role(project_id, user_id) is not None

    def can_edit_project(self, project_id: str, user_id: str) -> bool:
        """Check if a user can mutate project content."""
        return self.get_project_role(project_id, user_id) in PROJECT_EDIT_ROLES

    def can_manage_project(self, project_id: str, user_id: str) -> bool:
        """Check if a user can manage project sharing and deletion."""
        return self.get_project_role(project_id, user_id) == PROJECT_OWNER

    def list_project_members(
        self,
        project_id: str,
        requester_user_id: str,
    ) -> List[Dict[str, Any]]:
        """List explicit private-project members."""
        if not self.has_project_access(project_id, requester_user_id):
            raise PermissionError("Project access required")
        response = (
            self.supabase.table("project_members")
            .select("user_id, role, created_at, updated_at")
            .eq("project_id", project_id)
            .execute()
        )
        rows = response.data or []
        emails = self._emails_by_user_id([str(row["user_id"]) for row in rows if row.get("user_id")])
        return [
            {
                "user_id": str(row["user_id"]),
                "email": emails.get(str(row["user_id"])),
                "role": row.get("role") or PROJECT_VIEWER,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ]

    def add_project_member(
        self,
        project_id: str,
        target_user_id: str,
        role: str,
        requester_user_id: str,
    ) -> Dict[str, Any]:
        """Add an existing workspace member to a private project."""
        if role not in PROJECT_ROLES:
            raise ValueError("role must be owner, editor, or viewer")
        if not self.can_manage_project(project_id, requester_user_id):
            raise PermissionError("Project owner role required")
        project = self.get_project(project_id, user_id=requester_user_id)
        if not project:
            raise ValueError("Project not found")
        workspace_id = project.get("workspace_id")
        if not workspace_id or not self.has_workspace_access(workspace_id, target_user_id):
            raise PermissionError("User must be a workspace member before project sharing")

        response = (
            self.supabase.table("project_members")
            .upsert(
                {
                    "project_id": project_id,
                    "user_id": target_user_id,
                    "role": role,
                },
                on_conflict="project_id,user_id",
            )
            .execute()
        )
        row = response.data[0] if response.data else {
            "user_id": target_user_id,
            "role": role,
            "created_at": None,
            "updated_at": None,
        }
        row["email"] = self._emails_by_user_id([target_user_id]).get(target_user_id)
        return row

    def update_project_member_role(
        self,
        project_id: str,
        target_user_id: str,
        role: str,
        requester_user_id: str,
    ) -> Dict[str, Any]:
        """Update a private-project member role."""
        if role not in PROJECT_ROLES:
            raise ValueError("role must be owner, editor, or viewer")
        if not self.can_manage_project(project_id, requester_user_id):
            raise PermissionError("Project owner role required")
        current_role = self.get_project_role(project_id, target_user_id)
        if current_role is None:
            raise ValueError("Project member not found")
        if current_role == PROJECT_OWNER and role != PROJECT_OWNER:
            self._ensure_another_project_owner(project_id, target_user_id)

        response = (
            self.supabase.table("project_members")
            .update({"role": role})
            .eq("project_id", project_id)
            .eq("user_id", target_user_id)
            .execute()
        )
        if not response.data:
            raise ValueError("Project member not found")
        row = response.data[0]
        row["email"] = self._emails_by_user_id([target_user_id]).get(target_user_id)
        return row

    def remove_project_member(
        self,
        project_id: str,
        target_user_id: str,
        requester_user_id: str,
    ) -> bool:
        """Remove a private-project member."""
        if not self.can_manage_project(project_id, requester_user_id):
            raise PermissionError("Project owner role required")
        current_role = self.get_project_role(project_id, target_user_id)
        if current_role is None:
            return False
        if current_role == PROJECT_OWNER:
            self._ensure_another_project_owner(project_id, target_user_id)
        self.supabase.table("project_members").delete().eq(
            "project_id", project_id
        ).eq("user_id", target_user_id).execute()
        return True

    def _ensure_another_project_owner(self, project_id: str, excluded_user_id: str) -> None:
        response = (
            self.supabase.table("project_members")
            .select("user_id")
            .eq("project_id", project_id)
            .eq("role", PROJECT_OWNER)
            .neq("user_id", excluded_user_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise ValueError("Project must keep at least one owner")

    def _emails_by_user_id(self, user_ids: List[str]) -> Dict[str, Optional[str]]:
        if not user_ids:
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


# Singleton instance
project_service = ProjectStore()
