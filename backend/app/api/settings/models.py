"""
Model settings endpoints - Workspace-configurable Claude model per use case.

Educational Note: Every prompt config has a baked-in model (Haiku, Sonnet, or
Opus). This endpoint lets a workspace owner/admin override those models per
category:

    - chat:       main conversation, auto-naming, memory
    - studio:     all content generation (audio, video, presentations, etc.)
    - query:      database/csv/freshdesk analyzer agents
    - extraction: background source processing (PDF, PPTX, image, CSV)

Selecting "Default" (null) for a category clears the override so each prompt's
own JSON-baked model is used — preserving intentional per-prompt tuning like
presentation_agent=Opus.

Overrides are stored in workspace settings in Supabase mode, with .env kept as
the local/bootstrap fallback. PromptConfig resolves the model dynamically on
each request.

Routes:
- GET  /settings/models - Current overrides + available models + categories
- POST /settings/models - Set or clear overrides
"""
from flask import jsonify, request, current_app

from app.api.settings import settings_bp
from app.api.settings.workspace import resolve_workspace_context
from app.config.model import (
    AVAILABLE_MODELS,
    MODEL_CATEGORIES,
    get_current_settings,
    get_all_default_models,
)
from app.settings.env import EnvService
from app.workspaces.settings import workspace_settings_store

env_service = EnvService()


def _get_workspace_model_settings(workspace_id: str, requester_user_id: str) -> dict[str, str | None]:
    settings = get_current_settings()
    if not workspace_settings_store.supabase:
        return settings
    workspace_settings = workspace_settings_store.get_settings(workspace_id, requester_user_id)
    overrides = workspace_settings.get("model_overrides") or {}
    for category, model_id in overrides.items():
        if category in MODEL_CATEGORIES:
            settings[category] = model_id or None
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
                "chat": "claude-opus-4-6" | null,
                "studio": "claude-haiku-4-5-20251001" | null,
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
        identity, workspace_id = resolve_workspace_context(require_manager=True)
        # `defaults` shows what each prompt actually resolves to when its
        # category is set to "Default" — used by the UI to make Default
        # honest about which models will be used (e.g. chat = mostly Sonnet
        # but Haiku for chat_naming/memory).
        defaults = get_all_default_models()
        return jsonify({
            'success': True,
            'settings': _get_workspace_model_settings(workspace_id, identity.user_id),
            'available_models': list(AVAILABLE_MODELS.values()),
            'categories': list(MODEL_CATEGORIES.values()),
            'defaults': defaults,
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
            "chat": "claude-opus-4-6",          // set override
            "studio": null,                      // clear override (use Default)
            "query": "claude-haiku-4-5-20251001",
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
        validated: dict[str, str] = {}
        for category, model_id in data.items():
            if category not in MODEL_CATEGORIES:
                return jsonify({
                    'success': False,
                    'error': f"Unknown category: {category}. Must be one of: {list(MODEL_CATEGORIES.keys())}"
                }), 400

            if model_id in (None, ""):
                validated[category] = ""  # empty string = clear override
                continue

            if not isinstance(model_id, str) or model_id not in AVAILABLE_MODELS:
                return jsonify({
                    'success': False,
                    'error': f"Invalid model for {category}: {model_id}. Must be one of: {list(AVAILABLE_MODELS.keys())}"
                }), 400

            validated[category] = model_id

        # Apply all validated updates
        if workspace_settings_store.supabase:
            workspace_settings = workspace_settings_store.get_settings(workspace_id, identity.user_id)
            overrides = dict(workspace_settings.get("model_overrides") or {})
            for category, value in validated.items():
                overrides[category] = value or None
                current_app.logger.info(
                    "Updated workspace model override %s to %r",
                    category,
                    value or "<cleared>",
                )
            workspace_settings_store.update_settings(
                workspace_id,
                identity.user_id,
                {"model_overrides": overrides},
            )
        else:
            for category, value in validated.items():
                env_var = MODEL_CATEGORIES[category]["env_var"]
                env_service.set_key(env_var, value)
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
