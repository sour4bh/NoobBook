"""Workspace-scoped settings and encrypted provider secrets."""

import base64
import hashlib
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from app.providers.supabase import get_supabase, is_supabase_enabled
from app.workspaces.store import workspace_store

WORKSPACE_SECRET_KEY_ENV = "NOOBBOOK_WORKSPACE_SECRET_KEY"

KEY_PROVIDERS: Dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic",
    "ELEVENLABS_API_KEY": "elevenlabs",
    "OPENAI_API_KEY": "openai",
    "GEMINI_2_5_API_KEY": "google",
    "NANO_BANANA_API_KEY": "google",
    "VEO_API_KEY": "google",
    "PINECONE_API_KEY": "pinecone",
    "PINECONE_INDEX_NAME": "pinecone",
    "PINECONE_REGION": "pinecone",
    "TAVILY_API_KEY": "tavily",
    "GOOGLE_CLIENT_ID": "google",
    "GOOGLE_CLIENT_SECRET": "google",
    "WEBSHARE_API_KEY": "webshare",
    "NOTION_API_KEY": "notion",
    "JIRA_CLOUD_ID": "jira",
    "JIRA_EMAIL": "jira",
    "JIRA_API_KEY": "jira",
    "FRESHDESK_DOMAIN": "freshdesk",
    "FRESHDESK_API_KEY": "freshdesk",
    "MIXPANEL_SERVICE_ACCOUNT_USERNAME": "mixpanel",
    "MIXPANEL_SERVICE_ACCOUNT_SECRET": "mixpanel",
    "MIXPANEL_PROJECT_ID": "mixpanel",
    "MIXPANEL_REGION": "mixpanel",
    "OPIK_API_KEY": "opik",
    "OPIK_WORKSPACE": "opik",
    "OPIK_PROJECT_NAME": "opik",
    "OPIK_URL_OVERRIDE": "opik",
}


def _fernet() -> Fernet:
    secret = (os.getenv(WORKSPACE_SECRET_KEY_ENV) or "").strip()
    if not secret:
        raise RuntimeError(f"{WORKSPACE_SECRET_KEY_ENV} is required for workspace provider secrets")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def provider_for_key(key: str) -> str:
    return KEY_PROVIDERS.get(key, key.split("_", 1)[0].lower())


class WorkspaceSettingsStore:
    """Owns workspace JSON settings and encrypted provider secret data."""

    def __init__(self) -> None:
        self.supabase = get_supabase() if is_supabase_enabled() else None

    def resolve_workspace_id(
        self,
        *,
        user_id: str,
        email: Optional[str],
        requested_workspace_id: Optional[str] = None,
    ) -> str:
        """Resolve an explicit or selected workspace id for settings APIs."""
        if requested_workspace_id:
            return requested_workspace_id
        context = workspace_store.session_context(user_id=user_id, email=email)
        selected = context.get("selected_workspace") or {}
        workspace_id = selected.get("id")
        if not workspace_id:
            raise ValueError("workspace_id is required")
        return str(workspace_id)

    def get_settings(self, workspace_id: str, requester_user_id: str) -> Dict[str, Any]:
        """Return non-secret workspace settings visible to members."""
        if not self.supabase:
            return {}
        if not workspace_store.has_workspace_access(workspace_id, requester_user_id):
            raise PermissionError("Workspace access required")
        response = (
            self.supabase.table("workspaces")
            .select("settings")
            .eq("id", workspace_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise ValueError("Workspace not found")
        return response.data[0].get("settings") or {}

    def update_settings(
        self,
        workspace_id: str,
        requester_user_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge a patch into workspace settings. Requires workspace manager."""
        if not workspace_store.can_manage_workspace(workspace_id, requester_user_id):
            raise PermissionError("Workspace owner or admin role required")
        if not self.supabase:
            return patch
        current = self.get_settings(workspace_id, requester_user_id)
        updated = {**current, **patch}
        response = (
            self.supabase.table("workspaces")
            .update({"settings": updated})
            .eq("id", workspace_id)
            .execute()
        )
        if not response.data:
            raise ValueError("Workspace not found")
        return response.data[0].get("settings") or updated

    def get_provider_secret(self, workspace_id: str, key: str) -> Optional[str]:
        """Return a decrypted workspace provider secret, if present."""
        if not self.supabase:
            return None
        response = (
            self.supabase.table("workspace_provider_secrets")
            .select("encrypted_value")
            .eq("workspace_id", workspace_id)
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return decrypt_secret(str(response.data[0]["encrypted_value"]))

    def has_provider_secret(self, workspace_id: str, key: str) -> bool:
        if not self.supabase:
            return False
        response = (
            self.supabase.table("workspace_provider_secrets")
            .select("id")
            .eq("workspace_id", workspace_id)
            .eq("key", key)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def set_provider_secret(
        self,
        workspace_id: str,
        key: str,
        value: str,
        requester_user_id: str,
    ) -> None:
        """Encrypt and store a provider secret. Requires workspace manager."""
        if not workspace_store.can_manage_workspace(workspace_id, requester_user_id):
            raise PermissionError("Workspace owner or admin role required")
        if not self.supabase:
            return
        self.supabase.table("workspace_provider_secrets").upsert(
            {
                "workspace_id": workspace_id,
                "provider": provider_for_key(key),
                "key": key,
                "encrypted_value": encrypt_secret(value),
            },
            on_conflict="workspace_id,provider,key",
        ).execute()

    def delete_provider_secret(
        self,
        workspace_id: str,
        key: str,
        requester_user_id: str,
    ) -> None:
        """Delete a workspace provider secret. Requires workspace manager."""
        if not workspace_store.can_manage_workspace(workspace_id, requester_user_id):
            raise PermissionError("Workspace owner or admin role required")
        if not self.supabase:
            return
        self.supabase.table("workspace_provider_secrets").delete().eq(
            "workspace_id", workspace_id
        ).eq("key", key).execute()

    def get_project_provider_secret(self, project_id: Optional[str], key: str) -> Optional[str]:
        """Resolve a provider secret through a project's workspace."""
        if not project_id or not self.supabase:
            return None
        response = (
            self.supabase.table("projects")
            .select("workspace_id")
            .eq("id", project_id)
            .limit(1)
            .execute()
        )
        if not response.data or not response.data[0].get("workspace_id"):
            return None
        return self.get_provider_secret(str(response.data[0]["workspace_id"]), key)

    def get_runtime_settings(self, workspace_id: str) -> Dict[str, Any]:
        """Return workspace settings for trusted server-side project execution."""
        if not workspace_id or not self.supabase:
            return {}
        response = (
            self.supabase.table("workspaces")
            .select("settings")
            .eq("id", workspace_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return {}
        return response.data[0].get("settings") or {}

    def get_project_settings(self, project_id: Optional[str]) -> Dict[str, Any]:
        """Resolve non-secret runtime settings through a project's workspace."""
        if not project_id or not self.supabase:
            return {}
        response = (
            self.supabase.table("projects")
            .select("workspace_id")
            .eq("id", project_id)
            .limit(1)
            .execute()
        )
        if not response.data or not response.data[0].get("workspace_id"):
            return {}
        return self.get_runtime_settings(str(response.data[0]["workspace_id"]))

    def get_runtime_secret(
        self,
        key: str,
        *,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        env_fallback: bool = True,
    ) -> Optional[str]:
        """Resolve workspace-scoped secret, then optional `.env` fallback."""
        value = None
        if workspace_id:
            value = self.get_provider_secret(workspace_id, key)
        elif project_id:
            value = self.get_project_provider_secret(project_id, key)
        if value:
            return value
        return os.getenv(key) if env_fallback else None


workspace_settings_store = WorkspaceSettingsStore()
