from app.auth.asset_tokens import build_asset_token, parse_asset_token


def test_asset_token_round_trips_user_id():
    token = build_asset_token("user-123", "test-secret")

    assert parse_asset_token(token, "test-secret") == "user-123"


def test_asset_token_rejects_wrong_secret():
    token = build_asset_token("user-123", "test-secret")

    assert parse_asset_token(token, "other-secret") is None


def test_asset_token_rejects_expired_token():
    token = build_asset_token("user-123", "test-secret")

    assert parse_asset_token(token, "test-secret", max_age_seconds=-1) is None
