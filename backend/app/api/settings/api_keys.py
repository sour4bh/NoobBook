"""
API Key management endpoints.

Educational Note: Managing API keys securely is critical for any LLM application.
This module demonstrates several security patterns:

1. Key Masking:
   - Never send full API keys to frontend
   - Show only first/last few characters: "sk-...xyz"
   - Detect masked values on update (skip re-saving)

2. Key Validation:
   - Test keys before saving by making minimal API calls
   - Each service has its own validation logic
   - Validation happens server-side (keys never leave backend)

3. Workspace Storage:
   - In Supabase mode, keys are encrypted per workspace in
     workspace_provider_secrets.
   - .env keys remain a bootstrap/default fallback for local or global
     deployments.

4. Auto-Configuration:
   - Some keys trigger automatic setup (e.g., Pinecone creates index)
   - Related settings saved automatically (index name, region)

Supported API Keys:
- ANTHROPIC_API_KEY: Claude AI models
- ELEVENLABS_API_KEY: Speech-to-text
- OPENAI_API_KEY: Embeddings
- PINECONE_API_KEY: Vector database (+ auto-creates index)
- TAVILY_API_KEY: Web search
- GOOGLE_CLIENT_ID/SECRET: Google Drive OAuth
- GEMINI/VEO/NANO_BANANA: Google AI services
- NOTION_API_KEY: Notion integration (chat tools)
- JIRA_CLOUD_ID/EMAIL/API_KEY: Jira integration (chat tools)

Routes:
- GET    /settings/api-keys           - List all keys (masked)
- POST   /settings/api-keys           - Update keys
- DELETE /settings/api-keys/<key_id>  - Delete a key
- POST   /settings/api-keys/validate  - Validate a key

Env-reload → service-reload sequence (NBB-208A).
`update_api_keys` runs the following sequence so running services pick up new
credentials without a process restart:

1. For each incoming key that is not masked, call `env_service.set_key(...)`.
   `EnvService.set_key` writes the `.env` file via python-dotenv and also
   assigns `os.environ[key]` in-process.
2. Call `env_service.save()` (a no-op kept for API symmetry — python-dotenv
   persists on `set_key`/`unset_key`).
3. Call `env_service.reload_env()` — runs `load_dotenv(override=True)` so any
   indirectly cached readers see the new value.
4. Call the per-service `reload_config()` hook for each key whose owning
   integration caches config. The settings API is the single caller
   responsible for these hooks; integration services do not self-reload.

Validator ↔ reload-hook ownership map (inventory, NBB-208A; reconciled by
NBB-806).
This table names the current validator-body location and destination root.
Provider validators moved under `app.providers` in NBB-806; connector
validators moved beside their connector clients in NBB-807.

| key_id(s)                               | validator current location                                             | reload hook                                  | owner |
|-----------------------------------------|------------------------------------------------------------------------|-----------------------------------------------|------------------------------|
| `ANTHROPIC_API_KEY`                     | `providers/anthropic/validation.py`                                    | indirect via `claude_service.reload_config()` | `providers/` (raw client)   |
| `OPENAI_API_KEY`                        | `providers/openai/validation.py`                                       | none (embedding client is stateless)         | `providers/`                |
| `ELEVENLABS_API_KEY`                    | `providers/elevenlabs/validation.py`                                   | none                                          | `providers/`                |
| `GEMINI_2_5_API_KEY`                    | `providers/google/validation.py`                                       | none                                          | `providers/`                |
| `NANO_BANANA_API_KEY`                   | `providers/google/validation.py`                                       | none                                          | `providers/`                |
| `VEO_API_KEY`                           | `providers/google/validation.py`                                       | none                                          | `providers/`                |
| `PINECONE_API_KEY` + index/region       | `providers/pinecone/validation.py` (auto-saves index+region)           | none                                          | `providers/`                |
| `TAVILY_API_KEY`                        | `providers/tavily/validation.py`                                       | none                                          | `providers/`                |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | accepted-if-present                                                | none (OAuth flow reads env per request)      | `connectors/` (Google Drive)|
| `WEBSHARE_API_KEY`                      | accepted-if-present                                                    | none                                          | `providers/`                |
| `NOTION_API_KEY`                        | `connectors/notion/validation.py`                                      | `notion_client.reload_config()`              | `connectors/`               |
| `JIRA_API_KEY` + `JIRA_EMAIL` + `JIRA_CLOUD_ID` | `connectors/jira/validation.py` (needs email + cloud_id from env) | `jira_client.reload_config()`        | `connectors/`               |
| `FRESHDESK_API_KEY` + `FRESHDESK_DOMAIN` | `connectors/freshdesk/validation.py`                                  | `freshdesk_service.reload_config()`           | `connectors/`               |
| `MIXPANEL_SERVICE_ACCOUNT_*` + region/project | `connectors/mixpanel/validation.py`                              | `mixpanel_client.reload_config()`            | `connectors/`               |
| `OPIK_*`                                | `providers/opik/validation.py` (OPIK_API_KEY only; the rest are accepted-if-present) | `claude_service.reload_config()` (re-wraps client) | `providers/` (observability attached to Claude client) |

Validator-ownership rule (NBB-208A).
- `settings/` owns the validate endpoint, the `.env` CRUD orchestration, and
  the `app.settings.validation` module that routes key_ids to individual
  validators.
- `providers/` owns raw SDK health-check calls for provider keys.
- `connectors/` will own product-capability validation for configured
  product integrations (Notion, Jira, Freshdesk, Mixpanel, Google Drive).
  These move with the connector in `NBB-807`.
- Supporting-field acceptance ("Value accepted" for fields like
  `JIRA_CLOUD_ID`, `MIXPANEL_REGION`) stays inside `settings/` — no SDK call
  is involved.

App-factory touch points for this surface (see `backend/app/__init__.py`).
- Every endpoint resolves selected workspace context and requires workspace
  owner/admin role before exposing or mutating secrets.
- `env_service.reload_env()` relies on `.env` living under
  `self.backend_dir = Path(__file__).parent.parent.parent` from
  `app.settings.env` (`backend/.env`); future moves must preserve this
  resolution.

Stateless-deployment note.
Runtime `.env` writes assume a persistent container filesystem. On ECS
Fargate or Lambda, use environment injection instead — see `EnvService`
docstring.
"""
from flask import jsonify, request, current_app
from app.api.settings import settings_bp
from app.api.settings.workspace import resolve_workspace_context
from app.settings.env import EnvService
from app.settings import validation
from app.workspaces.settings import workspace_settings_store

# Initialize services
env_service = EnvService()

# API keys configuration - defines all managed keys
API_KEYS_CONFIG = [
    {
        'id': 'ANTHROPIC_API_KEY',
        'name': 'Anthropic API',
        'description': 'Claude AI models for chat',
        'category': 'ai',
        'required': True
    },
    {
        'id': 'ELEVENLABS_API_KEY',
        'name': 'ElevenLabs API',
        'description': 'Real-time speech-to-text transcription',
        'category': 'ai',
        'required': True
    },
    {
        'id': 'OPENAI_API_KEY',
        'name': 'OpenAI API',
        'description': 'OpenAI models for embeddings (text-embedding-3-small)',
        'category': 'ai'
    },
    {
        'id': 'GEMINI_2_5_API_KEY',
        'name': 'Gemini 2.5',
        'description': 'Google Gemini 2.5 text generation',
        'category': 'ai'
    },
    {
        'id': 'NANO_BANANA_API_KEY',
        'name': 'Nano Banana',
        'description': 'Gemini 3 Pro Image generation',
        'category': 'ai'
    },
    {
        'id': 'VEO_API_KEY',
        'name': 'VEO',
        'description': 'Google VEO 2.0 video generation',
        'category': 'ai'
    },
    {
        'id': 'PINECONE_API_KEY',
        'name': 'Pinecone API Key',
        'description': 'Vector database - auto-creates index on validation',
        'category': 'storage'
    },
    {
        'id': 'PINECONE_INDEX_NAME',
        'name': 'Pinecone Index Name',
        'description': 'Auto-managed (set after API key validation)',
        'category': 'storage'
    },
    {
        'id': 'PINECONE_REGION',
        'name': 'Pinecone Region',
        'description': 'Auto-managed (set after API key validation)',
        'category': 'storage'
    },
    {
        'id': 'TAVILY_API_KEY',
        'name': 'Tavily AI',
        'description': 'Web search AI',
        'category': 'utility'
    },
    {
        'id': 'GOOGLE_CLIENT_ID',
        'name': 'Google Client ID',
        'description': 'Google OAuth client ID for Drive integration',
        'category': 'utility'
    },
    {
        'id': 'GOOGLE_CLIENT_SECRET',
        'name': 'Google Client Secret',
        'description': 'Google OAuth client secret for Drive integration',
        'category': 'utility'
    },
    {
        'id': 'WEBSHARE_API_KEY',
        'name': 'Webshare Proxy',
        'description': 'Proxy rotation for YouTube transcript fetching',
        'category': 'utility'
    },
    {
        'id': 'NOTION_API_KEY',
        'name': 'Notion Integration',
        'description': 'Notion API key — enables Claude to search and read Notion pages in chat',
        'category': 'integrations'
    },
    {
        'id': 'JIRA_CLOUD_ID',
        'name': 'Jira Cloud ID',
        'description': 'Atlassian Cloud ID (from admin.atlassian.com → your-site → Settings)',
        'category': 'integrations'
    },
    {
        'id': 'JIRA_EMAIL',
        'name': 'Jira Email',
        'description': 'Atlassian account email for API authentication',
        'category': 'integrations'
    },
    {
        'id': 'JIRA_API_KEY',
        'name': 'Jira API Token',
        'description': 'Atlassian API token (from id.atlassian.com/manage-profile/security/api-tokens)',
        'category': 'integrations'
    },
    {
        'id': 'FRESHDESK_DOMAIN',
        'name': 'Freshdesk Domain',
        'description': 'Your Freshdesk subdomain (e.g. company.freshdesk.com)',
        'category': 'integrations'
    },
    {
        'id': 'FRESHDESK_API_KEY',
        'name': 'Freshdesk API Key',
        'description': 'Freshdesk API key (from Profile Settings > API Key)',
        'category': 'integrations'
    },
    {
        'id': 'MIXPANEL_SERVICE_ACCOUNT_USERNAME',
        'name': 'Mixpanel Service Account Username',
        'description': 'Service account username (Mixpanel → Project settings → Service Accounts)',
        'category': 'integrations'
    },
    {
        'id': 'MIXPANEL_SERVICE_ACCOUNT_SECRET',
        'name': 'Mixpanel Service Account Secret',
        'description': 'Service account secret (shown only at creation time)',
        'category': 'integrations'
    },
    {
        'id': 'MIXPANEL_PROJECT_ID',
        'name': 'Mixpanel Project ID',
        'description': 'Numeric project ID (Mixpanel → Project settings → Overview)',
        'category': 'integrations'
    },
    {
        'id': 'MIXPANEL_REGION',
        'name': 'Mixpanel Region',
        'description': 'Data residency region: us (default), eu, or in',
        'category': 'integrations'
    },
    {
        'id': 'OPIK_API_KEY',
        'name': 'Opik API Key',
        'description': 'Opik LLM observability — auto-traces all Claude calls (comet.com/opik)',
        'category': 'observability'
    },
    {
        'id': 'OPIK_WORKSPACE',
        'name': 'Opik Workspace',
        'description': 'Opik workspace name from your dashboard',
        'category': 'observability'
    },
    {
        'id': 'OPIK_PROJECT_NAME',
        'name': 'Opik Project Name',
        'description': 'Project name in Opik dashboard (default: NoobBook)',
        'category': 'observability'
    },
    {
        'id': 'OPIK_URL_OVERRIDE',
        'name': 'Opik URL Override',
        'description': 'Custom URL for self-hosted Opik (leave empty for Opik Cloud)',
        'category': 'observability'
    },
]


@settings_bp.route('/settings/api-keys', methods=['GET'])
def get_api_keys():
    """
    Get all API keys (with values masked for security).

    Educational Note: We never send actual API key values to the frontend.
    Instead, we send masked versions (showing only first/last few characters).
    This prevents accidental exposure via browser dev tools, logs, etc.

    Returns:
        {
            "success": true,
            "api_keys": [
                {
                    "id": "ANTHROPIC_API_KEY",
                    "name": "Anthropic API",
                    "description": "...",
                    "category": "ai",
                    "required": true,
                    "value": "sk-a...xyz",  # masked
                    "is_set": true
                },
                ...
            ]
        }
    """
    try:
        _identity, workspace_id = resolve_workspace_context(require_manager=True)
        api_keys = []
        for key_config in API_KEYS_CONFIG:
            value = (
                workspace_settings_store.get_provider_secret(workspace_id, key_config['id'])
                or env_service.get_key(key_config['id'])
            )
            masked_value = env_service.mask_key(value) if value else ''
            has_workspace_value = workspace_settings_store.has_provider_secret(
                workspace_id,
                key_config['id'],
            )

            api_keys.append({
                'id': key_config['id'],
                'name': key_config['name'],
                'description': key_config['description'],
                'category': key_config['category'],
                'required': key_config.get('required', False),
                'value': masked_value,
                'is_set': bool(value),
                'source': 'workspace' if has_workspace_value else ('env_fallback' if value else None),
            })

        return jsonify({
            'success': True,
            'api_keys': api_keys
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error getting API keys: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/api-keys', methods=['POST'])
def update_api_keys():
    """
    Update API keys in the selected workspace and trigger config reloads.

    Educational Note: This endpoint demonstrates safe key update pattern:
    1. Skip masked values (haven't changed)
    2. Save new values to workspace secrets, or .env when Supabase is disabled
    3. Reload environment variables
    4. Verify keys were saved correctly

    The skip-masked pattern is important: when frontend loads keys,
    it gets masked values. If user doesn't change a key, it stays masked.
    We detect this and don't overwrite with the mask.

    Request Body:
        {
            "api_keys": [
                {"id": "ANTHROPIC_API_KEY", "value": "sk-ant-..."},
                {"id": "OPENAI_API_KEY", "value": "***masked***"}  # skipped
            ]
        }

    Returns:
        { "success": true, "message": "API keys updated successfully" }
    """
    try:
        identity, workspace_id = resolve_workspace_context(require_manager=True)
        data = request.get_json()
        if not data or 'api_keys' not in data:
            return jsonify({
                'success': False,
                'error': 'No API keys provided'
            }), 400

        api_keys = data['api_keys']
        current_app.logger.info(f"Received {len(api_keys)} keys to update")

        # Update each API key in the selected workspace, or .env in local mode.
        updated_count = 0
        for key_data in api_keys:
            key_id = key_data.get('id')
            value = key_data.get('value', '')

            # Skip if value is masked (starts with asterisks)
            if value and not value.startswith('***'):
                if workspace_settings_store.supabase:
                    workspace_settings_store.set_provider_secret(
                        workspace_id,
                        key_id,
                        value,
                        identity.user_id,
                    )
                else:
                    env_service.set_key(key_id, value)
                updated_count += 1
                current_app.logger.info(f"Updated API key: {key_id}")

        # Save and reload
        env_service.save()
        env_service.reload_env()

        # Verify keys were saved
        for key_data in api_keys:
            key_id = key_data.get('id')
            value = key_data.get('value', '')
            if value and not value.startswith('***'):
                saved_value = (
                    workspace_settings_store.get_provider_secret(workspace_id, key_id)
                    if workspace_settings_store.supabase
                    else env_service.get_key(key_id)
                )
                if not saved_value:
                    current_app.logger.error(f"Failed to verify {key_id} in environment!")

        # Reload integration service configs so they pick up new keys without restart
        for key_data in api_keys:
            key_id = key_data.get('id')
            value = key_data.get('value', '')
            if value and not value.startswith('***'):
                if key_id == 'NOTION_API_KEY':
                    from app.connectors.notion import client as notion_client
                    notion_client.reload_config()
                elif key_id in ('JIRA_API_KEY', 'JIRA_CLOUD_ID', 'JIRA_EMAIL'):
                    from app.connectors.jira import client as jira_client
                    jira_client.reload_config()
                elif key_id in ('FRESHDESK_API_KEY', 'FRESHDESK_DOMAIN'):
                    from app.connectors.freshdesk.client import freshdesk_service
                    freshdesk_service.reload_config()
                elif key_id in (
                    'MIXPANEL_SERVICE_ACCOUNT_USERNAME',
                    'MIXPANEL_SERVICE_ACCOUNT_SECRET',
                    'MIXPANEL_PROJECT_ID',
                    'MIXPANEL_REGION',
                ):
                    from app.connectors.mixpanel import client as mixpanel_client
                    mixpanel_client.reload_config()
                elif key_id in ('OPIK_API_KEY', 'OPIK_WORKSPACE', 'OPIK_PROJECT_NAME', 'OPIK_URL_OVERRIDE'):
                    # Reset Claude client so it re-initializes with/without Opik wrapping.
                    # NBB-208A: uses the public reload_config() hook to match Notion/Jira/etc.
                    from app.providers.anthropic.messages import claude_service
                    claude_service.reload_config()

        current_app.logger.info(f"Updated {updated_count} API keys")

        return jsonify({
            'success': True,
            'message': 'API keys updated successfully'
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error updating API keys: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/api-keys/<key_id>', methods=['DELETE'])
def delete_api_key(key_id):
    """
    Delete a specific API key from the selected workspace.

    Educational Note: This removes the workspace value entirely, not just
    clearing its value. For some keys, we also clean up
    related configuration (e.g., Pinecone index name and region).

    URL Parameters:
        key_id: The environment variable name (e.g., "ANTHROPIC_API_KEY")

    Returns:
        { "success": true, "message": "API key ... deleted successfully" }
    """
    try:
        identity, workspace_id = resolve_workspace_context(require_manager=True)
        # Delete the main key
        if workspace_settings_store.supabase:
            workspace_settings_store.delete_provider_secret(workspace_id, key_id, identity.user_id)
        else:
            env_service.delete_key(key_id)

        # If deleting Pinecone API key, also delete related config
        if key_id == 'PINECONE_API_KEY':
            current_app.logger.info("Deleting related Pinecone configuration...")
            if workspace_settings_store.supabase:
                workspace_settings_store.delete_provider_secret(
                    workspace_id,
                    'PINECONE_INDEX_NAME',
                    identity.user_id,
                )
                workspace_settings_store.delete_provider_secret(
                    workspace_id,
                    'PINECONE_REGION',
                    identity.user_id,
                )
            else:
                env_service.delete_key('PINECONE_INDEX_NAME')
                env_service.delete_key('PINECONE_REGION')

        env_service.save()
        env_service.reload_env()

        return jsonify({
            'success': True,
            'message': f'API key {key_id} deleted successfully'
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error deleting API key {key_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@settings_bp.route('/settings/api-keys/validate', methods=['POST'])
def validate_api_key():
    """
    Validate an API key by making a test request to the service.

    Educational Note: Validation tests if a key actually works by making
    a minimal API call to each service. This prevents users from saving
    invalid keys and only discovering the problem later.

    Each service has custom validation:
    - Anthropic: Makes a minimal completion request
    - OpenAI: Tests the embeddings endpoint
    - Pinecone: Checks/creates the index (auto-configures settings)
    - ElevenLabs: Tests token generation
    - Tavily: Makes a test search

    For Pinecone specifically, successful validation automatically:
    1. Creates the "growthxlearn" index if it doesn't exist
    2. Saves index name and region to the selected workspace

    Request Body:
        { "key_id": "ANTHROPIC_API_KEY", "value": "sk-ant-..." }

    Returns:
        {
            "success": true,
            "valid": true,
            "message": "API key is valid"
        }
    """
    try:
        identity, workspace_id = resolve_workspace_context(require_manager=True)
        data = request.get_json()
        if not data or 'key_id' not in data or 'value' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing key_id or value'
            }), 400

        key_id = data['key_id']
        value = data['value']

        # Skip validation for masked values (already validated)
        if value.startswith('***'):
            return jsonify({
                'success': True,
                'valid': True,
                'message': 'Key already set'
            }), 200

        # Validate based on key type
        is_valid, message = _validate_key(key_id, value, workspace_id, identity.user_id)

        current_app.logger.info(f"Validation result for {key_id}: {is_valid} - {message}")

        return jsonify({
            'success': True,
            'valid': is_valid,
            'message': message
        }), 200

    except PermissionError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 403
    except Exception as e:
        current_app.logger.error(f"Error validating API key: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _get_workspace_or_env(workspace_id: str, key: str) -> str | None:
    return workspace_settings_store.get_provider_secret(workspace_id, key) or env_service.get_key(key)


def _validate_key(
    key_id: str,
    value: str,
    workspace_id: str,
    requester_user_id: str,
) -> tuple[bool, str]:
    """
    Validate a specific API key using the appropriate validator.

    Educational Note: Each API service has different validation requirements.
    This function routes to the correct validator and handles special cases
    like Pinecone's auto-configuration.
    """
    if key_id == 'ANTHROPIC_API_KEY':
        return validation.validate_anthropic_key(value)

    elif key_id == 'ELEVENLABS_API_KEY':
        return validation.validate_elevenlabs_key(value)

    elif key_id == 'OPENAI_API_KEY':
        return validation.validate_openai_key(value)

    elif key_id == 'GEMINI_2_5_API_KEY':
        return validation.validate_gemini_2_5_key(value)

    elif key_id == 'NANO_BANANA_API_KEY':
        return validation.validate_nano_banana_key(value)

    elif key_id == 'VEO_API_KEY':
        return validation.validate_veo_key(value)

    elif key_id == 'TAVILY_API_KEY':
        return validation.validate_tavily_key(value)

    elif key_id == 'PINECONE_API_KEY':
        # Pinecone validation also creates/checks index
        is_valid, message, index_details = validation.validate_pinecone_key(value)

        # Auto-save index details on successful validation
        if is_valid and index_details:
            try:
                current_app.logger.info(f"Saving Pinecone index details: {index_details}")
                if workspace_settings_store.supabase:
                    workspace_settings_store.set_provider_secret(
                        workspace_id,
                        'PINECONE_INDEX_NAME',
                        index_details['index_name'],
                        requester_user_id,
                    )
                    workspace_settings_store.set_provider_secret(
                        workspace_id,
                        'PINECONE_REGION',
                        index_details['region'],
                        requester_user_id,
                    )
                else:
                    env_service.set_key('PINECONE_INDEX_NAME', index_details['index_name'])
                    env_service.set_key('PINECONE_REGION', index_details['region'])
                    env_service.save()
            except Exception as e:
                current_app.logger.error(f"Failed to save Pinecone index details: {e}")

        return is_valid, message

    elif key_id in ['PINECONE_INDEX_NAME', 'PINECONE_REGION']:
        # Auto-managed fields - just accept them
        is_valid = bool(value)
        message = 'Configuration accepted (auto-managed)'
        return is_valid, message

    elif key_id == 'NOTION_API_KEY':
        return validation.validate_notion_key(value)

    elif key_id == 'JIRA_API_KEY':
        # Jira validation needs email + cloud_id from workspace settings.
        jira_email = _get_workspace_or_env(workspace_id, 'JIRA_EMAIL')
        jira_cloud_id = _get_workspace_or_env(workspace_id, 'JIRA_CLOUD_ID')
        return validation.validate_jira_key(value, jira_email, jira_cloud_id)

    elif key_id in ['JIRA_CLOUD_ID', 'JIRA_EMAIL']:
        # Supporting fields for Jira — just accept them
        is_valid = bool(value)
        message = 'Value accepted' if is_valid else 'Value is empty'
        return is_valid, message

    elif key_id == 'FRESHDESK_API_KEY':
        freshdesk_domain = _get_workspace_or_env(workspace_id, 'FRESHDESK_DOMAIN')
        return validation.validate_freshdesk_key(value, freshdesk_domain)

    elif key_id == 'FRESHDESK_DOMAIN':
        # Supporting field — just accept it
        is_valid = bool(value)
        message = 'Value accepted' if is_valid else 'Value is empty'
        return is_valid, message

    elif key_id == 'MIXPANEL_SERVICE_ACCOUNT_SECRET':
        # Mixpanel validation needs supporting fields from workspace settings.
        mixpanel_username = _get_workspace_or_env(
            workspace_id,
            'MIXPANEL_SERVICE_ACCOUNT_USERNAME',
        )
        mixpanel_project_id = _get_workspace_or_env(workspace_id, 'MIXPANEL_PROJECT_ID')
        mixpanel_region = _get_workspace_or_env(workspace_id, 'MIXPANEL_REGION') or 'us'
        return validation.validate_mixpanel_key(
            value, mixpanel_username, mixpanel_project_id, mixpanel_region
        )

    elif key_id in ('MIXPANEL_SERVICE_ACCOUNT_USERNAME', 'MIXPANEL_PROJECT_ID', 'MIXPANEL_REGION'):
        # Supporting fields for Mixpanel — just accept them
        is_valid = bool(value)
        message = 'Value accepted' if is_valid else 'Value is empty'
        return is_valid, message

    elif key_id == 'OPIK_API_KEY':
        return validation.validate_opik_key(value)

    elif key_id in ['OPIK_WORKSPACE', 'OPIK_PROJECT_NAME', 'OPIK_URL_OVERRIDE']:
        is_valid = bool(value)
        message = 'Value accepted' if is_valid else 'Value is empty'
        return is_valid, message
    else:
        # Default validation - just check if value exists
        is_valid = bool(value)
        message = 'Key provided' if is_valid else 'Key is empty'
        return is_valid, message
