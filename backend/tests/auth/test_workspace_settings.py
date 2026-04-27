from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.providers.pinecone.index import PineconeService
from app.connectors.freshdesk.client import freshdesk_service
from app.connectors.jira.client import jira_service
from app.connectors.mixpanel.client import mixpanel_service
from app.connectors.notion.client import notion_service
from app.config.model import PromptModel, resolve_model_for_project
from app.config.provider import APIProvider, get_tier
from app.providers.elevenlabs import tts_service
from app.providers.google.imagen import imagen_service
from app.workspaces.settings import WorkspaceSettingsStore


def test_workspace_provider_secret_round_trips_encrypted(monkeypatch):
    monkeypatch.setenv("NOOBBOOK_WORKSPACE_SECRET_KEY", "test-secret")

    store = WorkspaceSettingsStore.__new__(WorkspaceSettingsStore)
    store.supabase = MagicMock()

    upsert_query = MagicMock()
    store.supabase.table.return_value.upsert.return_value = upsert_query

    with patch(
        "app.workspaces.settings.workspace_store.can_manage_workspace",
        return_value=True,
    ):
        store.set_provider_secret(
            "workspace-1",
            "ANTHROPIC_API_KEY",
            "sk-ant-workspace",
            "owner-1",
        )

    stored_row = store.supabase.table.return_value.upsert.call_args.args[0]
    assert stored_row["workspace_id"] == "workspace-1"
    assert stored_row["provider"] == "anthropic"
    assert stored_row["encrypted_value"] != "sk-ant-workspace"

    select_query = MagicMock()
    select_query.eq.return_value = select_query
    select_query.limit.return_value = select_query
    select_query.execute.return_value = SimpleNamespace(
        data=[{"encrypted_value": stored_row["encrypted_value"]}]
    )
    store.supabase.table.return_value.select.return_value = select_query

    assert store.get_provider_secret("workspace-1", "ANTHROPIC_API_KEY") == "sk-ant-workspace"


def test_api_key_update_stores_workspace_secret(auth_client, auth_optional_env):
    identity = SimpleNamespace(user_id="owner-1")

    with patch(
        "app.api.settings.api_keys.resolve_workspace_context",
        return_value=(identity, "workspace-1"),
    ), patch("app.api.settings.api_keys.workspace_settings_store") as settings:
        settings.supabase = object()

        response = auth_client.post(
            "/api/v1/settings/api-keys",
            json={
                "api_keys": [
                    {"id": "ANTHROPIC_API_KEY", "value": "sk-ant-workspace"}
                ]
            },
        )

    assert response.status_code == 200
    settings.set_provider_secret.assert_called_once_with(
        "workspace-1",
        "ANTHROPIC_API_KEY",
        "sk-ant-workspace",
        "owner-1",
    )


def test_api_key_update_rejects_workspace_member(auth_client, auth_optional_env):
    with patch(
        "app.api.settings.api_keys.resolve_workspace_context",
        side_effect=PermissionError("Workspace owner or admin role required"),
    ):
        response = auth_client.post(
            "/api/v1/settings/api-keys",
            json={
                "api_keys": [
                    {"id": "ANTHROPIC_API_KEY", "value": "sk-ant-workspace"}
                ]
            },
        )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Workspace owner or admin role required"


def test_pinecone_configuration_resolves_project_workspace_secret():
    service = PineconeService()

    with patch(
        "app.providers.pinecone.index.get_project_secret"
    ) as get_project_secret, patch(
        "app.providers.pinecone.index.get_secret"
    ) as settings, patch("app.providers.pinecone.index.Pinecone") as pinecone:
        get_project_secret.return_value = "workspace-pinecone-key"
        settings.return_value = "workspace-index"
        pinecone.return_value.has_index.return_value = True

        assert service.is_configured(project_id="project-1") is True

    pinecone.assert_called_once_with(api_key="workspace-pinecone-key")
    pinecone.return_value.has_index.assert_called_once_with("workspace-index")


def test_model_override_resolves_from_project_workspace_settings():
    model = PromptModel("claude-sonnet-4-6", prompt_name="default")

    with patch("app.config.secret.workspace_settings_store") as settings:
        settings.get_project_settings.return_value = {
            "model_overrides": {"chat": "claude-haiku-4-5-20251001"}
        }

        assert (
            resolve_model_for_project(model, "project-1")
            == "claude-haiku-4-5-20251001"
        )


def test_provider_tier_resolves_from_project_workspace_settings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_TIER", "1")

    with patch("app.config.secret.workspace_settings_store") as settings:
        settings.get_project_settings.return_value = {
            "provider_tiers": {APIProvider.ANTHROPIC.value: 3}
        }

        assert get_tier(APIProvider.ANTHROPIC.value, project_id="project-1") == 3


def test_connector_clients_resolve_project_workspace_secrets(monkeypatch):
    for key in (
        "NOTION_API_KEY",
        "JIRA_EMAIL",
        "JIRA_API_KEY",
        "JIRA_CLOUD_ID",
        "FRESHDESK_API_KEY",
        "FRESHDESK_DOMAIN",
        "MIXPANEL_SERVICE_ACCOUNT_USERNAME",
        "MIXPANEL_SERVICE_ACCOUNT_SECRET",
        "MIXPANEL_PROJECT_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    secrets = {
        "NOTION_API_KEY": "secret-notion",
        "JIRA_EMAIL": "jira@example.com",
        "JIRA_API_KEY": "secret-jira",
        "JIRA_CLOUD_ID": "cloud-123",
        "FRESHDESK_API_KEY": "secret-freshdesk",
        "FRESHDESK_DOMAIN": "example",
        "MIXPANEL_SERVICE_ACCOUNT_USERNAME": "mixpanel-user",
        "MIXPANEL_SERVICE_ACCOUNT_SECRET": "secret-mixpanel",
        "MIXPANEL_PROJECT_ID": "12345",
    }

    freshdesk_service.reload_config()
    with patch("app.config.secret.workspace_settings_store") as settings:
        settings.get_runtime_secret.side_effect = (
            lambda key, **_kwargs: secrets.get(key)
        )

        assert notion_service.is_configured(project_id="project-1") is True
        assert jira_service.is_configured(project_id="project-1") is True
        assert freshdesk_service.is_configured(project_id="project-1") is True
        assert mixpanel_service.is_configured(project_id="project-1") is True

    freshdesk_service.reload_config()


def test_studio_provider_status_resolves_workspace_secrets(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("NANO_BANANA_API_KEY", raising=False)

    secrets = {
        "ELEVENLABS_API_KEY": "secret-elevenlabs",
        "NANO_BANANA_API_KEY": "secret-gemini",
    }

    with patch("app.config.secret.workspace_settings_store") as settings:
        settings.get_runtime_secret.side_effect = (
            lambda key, **kwargs: secrets.get(key)
            if kwargs.get("workspace_id") == "workspace-1"
            else None
        )

        assert tts_service.is_configured(workspace_id="workspace-1") is True
        assert imagen_service.is_configured(workspace_id="workspace-1") is True
