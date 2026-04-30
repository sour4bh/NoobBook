"""
Model settings endpoints - workspace-configurable provider/model per use case.

Educational Note: Every prompt config has a baked-in provider/model pair. This
endpoint lets a workspace owner/admin override those selections per category:

    - chat:       main conversation, auto-naming, memory
    - studio:     all content generation (audio, video, presentations, etc.)
    - query:      database/csv/freshdesk analyzer agents
    - extraction: background source processing (PDF, PPTX, image, CSV)

Selecting "Default" (null) for a category clears the override so each typed
PromptSpec's provider/model is used.

Overrides are stored in workspace settings in Supabase mode, with .env kept as
the local/bootstrap fallback. Runtime prompt rendering resolves the model on
each request.

Routes:
- GET  /settings/models - Current overrides + available models + categories
- POST /settings/models - Set or clear overrides
"""
from flask import jsonify, request, current_app

from app.api.settings import settings_bp
from app.api.settings.workspace import resolve_workspace_context
from app.config.model import (
    MODEL_CATEGORIES,
    get_available_models,
    get_current_settings,
    get_all_default_models,
    get_configured_providers,
    normalize_model_selection,
    is_provider_configured,
    workspace_model_overrides,
)
from app.settings.env import EnvService
from app.workspaces.settings import workspace_settings_store
from app.workspaces.store import workspace_store

env_service = EnvService()


def _get_workspace_model_settings(
    workspace_id: str,
    requester_user_id: str,
) -> dict[str, dict[str, str] | None]:
    settings = get_current_settings()
    if not workspace_settings_store.supabase:
        return settings
    workspace_settings = workspace_settings_store.get_settings(workspace_id, requester_user_id)
    overrides = workspace_model_overrides(workspace_settings)
    for category, model_id in overrides.items():
        if category in MODEL_CATEGORIES:
            selection = normalize_model_selection(model_id)
            settings[category] = (
                selection.model_dump(mode="json")
                if selection
                and is_provider_configured(selection.provider, workspace_id=workspace_id)
                else None
            )
    return settings


@settings_bp.route('/settings/models', methods=['GET'])
def get_model_settings():
    """
    Return current per-category model overrides plus the lists needed to
    render the admin UI.

    Response:
        {
            "success": true,
            "settings": {
                "chat": {"provider": "anthropic", "model": "claude-opus-4-6"} | null,
                "studio": {"provider": "openai", "model": "gpt-5-mini"} | null,
                "query": null,
                "extraction": null
            },
            "available_models": [
                {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", ...},
                ...
            ],
            "categories": [
                {"id": "chat", "label": "Chat", "description": "...", "env_var": "CHAT_MODEL_OVERRIDE"},
                ...
            ]
        }
    """
    try:
        identity, workspace_id = resolve_workspace_context(require_manager=False)
        can_manage = workspace_store.can_manage_workspace(workspace_id, identity.user_id)
        # `defaults` shows what each prompt actually resolves to when its
        # category is set to "Default" — used by the UI to make Default
        # honest about which models will be used (e.g. chat = mostly Sonnet
        # but Haiku for chat_naming/memory).
        defaults = get_all_default_models()
        return jsonify({
            'success': True,
            'settings': _get_workspace_model_settings(workspace_id, identity.user_id),
            'available_models': get_available_models(workspace_id=workspace_id),
            'configured_providers': get_configured_providers(workspace_id=workspace_id),
            'categories': list(MODEL_CATEGORIES.values()),
            'defaults': defaults,
            'capabilities': {
                'can_manage_provider_keys': can_manage,
                'can_manage_model_defaults': can_manage,
            },
        }), 200
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        current_app.logger.error(f"Error getting model settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/settings/models', methods=['POST'])
def update_model_settings():
    """
    Update per-category model overrides.

    Request body:
        {
            "chat": {"provider": "anthropic", "model": "claude-opus-4-6"},
            "studio": null,                      // clear override (use Default)
            "query": {"provider": "openai", "model": "gpt-5-mini"},
            "extraction": null
        }

    Only categories present in the body are updated. Sending null or "" clears
    the override for that category. Unknown categories or invalid model ids
    return 400 without changing any values.
    """
    try:
        identity, workspace_id = resolve_workspace_context(require_manager=True)
        data = request.get_json()
        if data is None or not isinstance(data, dict):
            return jsonify({
                'success': False,
                'error': 'Request body must be a JSON object mapping category → model id or null'
            }), 400

        # Validate everything before writing anything so a single bad entry
        # doesn't leave the .env in a half-updated state.
        validated: dict[str, dict[str, str] | None] = {}
        for category, model_id in data.items():
            if category not in MODEL_CATEGORIES:
                return jsonify({
                    'success': False,
                    'error': f"Unknown category: {category}. Must be one of: {list(MODEL_CATEGORIES.keys())}"
                }), 400

            if model_id in (None, ""):
                validated[category] = None
                continue

            selection = normalize_model_selection(model_id)
            if selection is None:
                return jsonify({
                    'success': False,
                    'error': (
                        f"Invalid provider/model for {category}: {model_id}."
                    )
                }), 400

            if not is_provider_configured(selection.provider, workspace_id=workspace_id):
                return jsonify({
                    'success': False,
                    'error': (
                        f"{selection.provider} provider is not configured. "
                        "Save that provider's API key before selecting its models."
                    )
                }), 400

            validated[category] = selection.model_dump(mode="json")

        # Apply all validated updates
        if workspace_settings_store.supabase:
            workspace_settings = workspace_settings_store.get_settings(workspace_id, identity.user_id)
            ai_settings = dict(workspace_settings.get("ai") or {})
            overrides = workspace_model_overrides(workspace_settings)
            for category, value in validated.items():
                overrides[category] = value
                current_app.logger.info(
                    "Updated workspace model override %s to %r",
                    category,
                    value or "<cleared>",
                )
            workspace_settings_store.update_settings(
                workspace_id,
                identity.user_id,
                {"ai": {**ai_settings, "models": overrides}},
            )
        else:
            for category, value in validated.items():
                env_var = MODEL_CATEGORIES[category]["env_var"]
                env_service.set_key(env_var, value["model"] if value else "")
                current_app.logger.info(
                    "Updated %s to %r", env_var, value or "<cleared>"
                )
            env_service.reload_env()

        return jsonify({
            'success': True,
            'message': 'Model settings updated successfully',
            'settings': _get_workspace_model_settings(workspace_id, identity.user_id),
        }), 200

    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        current_app.logger.error(f"Error updating model settings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
