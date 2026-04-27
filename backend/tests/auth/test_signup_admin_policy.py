from types import SimpleNamespace
from unittest.mock import MagicMock


def _auth_service():
    from app.providers.supabase.auth import AuthService

    service = object.__new__(AuthService)
    service.supabase = MagicMock()
    return service


def test_public_signup_role_is_always_user(monkeypatch):
    monkeypatch.setenv("NOOBBOOK_ADMIN_EMAILS", "founder@example.com")
    service = _auth_service()

    assert service._resolve_signup_role("founder@example.com") == "user"
    assert service._resolve_signup_role("first@example.com") == "user"
    service.supabase.table.assert_not_called()


def test_sign_up_creates_user_profile_with_user_role(monkeypatch):
    monkeypatch.setenv("NOOBBOOK_ADMIN_EMAILS", "founder@example.com")
    service = _auth_service()
    service.supabase.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="founder@example.com"),
        session=SimpleNamespace(
            access_token="access",
            refresh_token="refresh",
            expires_in=3600,
            token_type="bearer",
        ),
    )

    result = service.sign_up("founder@example.com", "password")

    assert result["success"] is True
    users_table = service.supabase.table.return_value
    users_table.select.assert_not_called()
    users_table.insert.assert_called_once_with(
        {
            "id": "user-1",
            "email": "founder@example.com",
            "role": "user",
            "memory": {},
            "settings": {},
        }
    )


def test_bootstrap_admin_from_env_remains_explicit_admin_path(monkeypatch):
    service = _auth_service()
    monkeypatch.setenv("NOOBBOOK_BOOTSTRAP_ADMIN_EMAIL", "Admin@Example.com")
    monkeypatch.setenv("NOOBBOOK_BOOTSTRAP_ADMIN_PASSWORD", "correct-horse-battery-staple")
    monkeypatch.delenv("NOOBBOOK_BOOTSTRAP_ADMIN_FORCE_RESET", raising=False)
    service._find_user_by_email = MagicMock(return_value=None)
    service._ensure_user_profile = MagicMock()
    service.supabase.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="admin-1")
    )

    assert service.bootstrap_admin_from_env() is True
    service.supabase.auth.admin.create_user.assert_called_once_with(
        {
            "email": "admin@example.com",
            "password": "correct-horse-battery-staple",
            "email_confirm": True,
        }
    )
    service._ensure_user_profile.assert_called_once_with(
        "admin-1",
        "admin@example.com",
        role="admin",
    )
