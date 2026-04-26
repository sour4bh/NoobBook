"""
API-key validation: unified module-level façade.

Each provider has its own validator function in the legacy validator package.
This module exposes a single `validate(key_name, value, **extras)` dispatcher
plus the per-provider validator functions for direct call sites.

The previous `ValidationService` class held no state; NBB-706 collapses
it into module functions.
"""
from typing import Any, Tuple

from app.services.app_settings.validation.anthropic_validator import (
    validate_anthropic_key,
)
from app.services.app_settings.validation.elevenlabs_validator import (
    validate_elevenlabs_key,
)
from app.services.app_settings.validation.freshdesk_validator import (
    validate_freshdesk_key,
)
from app.services.app_settings.validation.gemini_validator import (
    validate_gemini_2_5_key,
)
from app.services.app_settings.validation.jira_validator import validate_jira_key
from app.services.app_settings.validation.mixpanel_validator import (
    validate_mixpanel_key,
)
from app.services.app_settings.validation.nano_banana_validator import (
    validate_nano_banana_key,
)
from app.services.app_settings.validation.notion_validator import (
    validate_notion_key,
)
from app.services.app_settings.validation.openai_validator import (
    validate_openai_key,
)
from app.services.app_settings.validation.opik_validator import validate_opik_key
from app.services.app_settings.validation.pinecone_validator import (
    validate_pinecone_key,
)
from app.services.app_settings.validation.tavily_validator import (
    validate_tavily_key,
)
from app.services.app_settings.validation.veo_validator import validate_veo_key

__all__ = [
    "validate",
    "validate_anthropic_key",
    "validate_elevenlabs_key",
    "validate_openai_key",
    "validate_gemini_2_5_key",
    "validate_nano_banana_key",
    "validate_veo_key",
    "validate_tavily_key",
    "validate_pinecone_key",
    "validate_notion_key",
    "validate_jira_key",
    "validate_freshdesk_key",
    "validate_mixpanel_key",
    "validate_opik_key",
]


def validate(key_name: str, value: str, **extras: Any) -> Tuple[bool, str]:
    """Dispatch validation by `key_name`.

    `extras` carries provider-specific supporting fields (e.g. Jira email,
    Freshdesk domain, Mixpanel project_id). Unknown keys raise `ValueError`.
    """
    if key_name == "ANTHROPIC_API_KEY":
        return validate_anthropic_key(value)
    if key_name == "ELEVENLABS_API_KEY":
        return validate_elevenlabs_key(value)
    if key_name == "OPENAI_API_KEY":
        return validate_openai_key(value)
    if key_name == "GEMINI_API_KEY":
        return validate_gemini_2_5_key(value)
    if key_name == "NANO_BANANA_API_KEY":
        return validate_nano_banana_key(value)
    if key_name == "VEO_API_KEY":
        return validate_veo_key(value)
    if key_name == "TAVILY_API_KEY":
        return validate_tavily_key(value)
    if key_name == "PINECONE_API_KEY":
        ok, msg, _details = validate_pinecone_key(value)
        return ok, msg
    if key_name == "NOTION_API_KEY":
        return validate_notion_key(value)
    if key_name == "JIRA_API_KEY":
        return validate_jira_key(value, extras.get("email"), extras.get("cloud_id"))
    if key_name == "FRESHDESK_API_KEY":
        return validate_freshdesk_key(value, extras.get("domain"))
    if key_name == "MIXPANEL_SERVICE_ACCOUNT_SECRET":
        return validate_mixpanel_key(
            value,
            extras.get("username"),
            extras.get("project_id"),
            extras.get("region"),
        )
    if key_name == "OPIK_API_KEY":
        return validate_opik_key(value)
    raise ValueError(f"No validator registered for key_name={key_name!r}")
