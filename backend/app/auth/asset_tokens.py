"""Scoped browser-asset access tokens."""

from typing import Any, Optional

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer


ASSET_TOKEN_MAX_AGE_SECONDS = 15 * 60
_ASSET_TOKEN_SALT = "noobbook.asset-access"
_ASSET_TOKEN_SCOPE = "browser_asset"
_ASSET_TOKEN_VERSION = 1


def build_asset_token(user_id: str, secret_key: str) -> str:
    """Build a short-lived token for browser-loaded asset routes."""
    serializer = URLSafeTimedSerializer(secret_key=secret_key, salt=_ASSET_TOKEN_SALT)
    payload = {
        "scope": _ASSET_TOKEN_SCOPE,
        "version": _ASSET_TOKEN_VERSION,
        "user_id": user_id,
    }
    return serializer.dumps(payload)


def parse_asset_token(
    token: str,
    secret_key: str,
    max_age_seconds: int = ASSET_TOKEN_MAX_AGE_SECONDS,
) -> Optional[str]:
    """Return the scoped user_id, or None when the token is invalid/expired."""
    if not token:
        return None

    serializer = URLSafeTimedSerializer(secret_key=secret_key, salt=_ASSET_TOKEN_SALT)
    try:
        payload: Any = serializer.loads(token, max_age=max_age_seconds)
    except (BadData, SignatureExpired):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("scope") != _ASSET_TOKEN_SCOPE:
        return None
    if payload.get("version") != _ASSET_TOKEN_VERSION:
        return None

    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        return None
    return user_id
