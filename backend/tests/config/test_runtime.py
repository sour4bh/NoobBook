"""Runtime config tests for the NBB-902 Pydantic settings move."""

from pathlib import Path

from flask import Flask

from app.config.runtime import Config, RuntimeSettings


def test_runtime_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    monkeypatch.delenv("API_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)

    settings = RuntimeSettings(_env_file=tmp_path / "missing.env")

    assert settings.app_name == "NoobBook"
    assert settings.api_prefix == "/api/v1"
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    assert settings.frontend_redirect_origin == "http://localhost:5173"
    assert settings.google_callback_url == "http://localhost:5001/api/v1/google/callback"


def test_runtime_settings_env_override(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALLOWED_ORIGINS=http://example.test,http://localhost:9999\n"
        "FRONTEND_ORIGIN=https://app.example.test/\n"
        "API_PUBLIC_ORIGIN=https://api.example.test/\n"
        "MAX_CONTENT_LENGTH=123\n",
        encoding="utf-8",
    )

    settings = RuntimeSettings(_env_file=env_file)

    assert settings.cors_allowed_origins == [
        "http://example.test",
        "http://localhost:9999",
    ]
    assert settings.frontend_redirect_origin == "https://app.example.test"
    assert settings.google_callback_url == "https://api.example.test/api/v1/google/callback"
    assert settings.max_content_length == 123


def test_runtime_settings_explicit_google_redirect_uri(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GOOGLE_OAUTH_REDIRECT_URI=https://oauth.example.test/google/callback\n",
        encoding="utf-8",
    )

    settings = RuntimeSettings(_env_file=env_file)

    assert settings.google_callback_url == "https://oauth.example.test/google/callback"


def test_backend_config_module_collision_is_removed() -> None:
    backend_dir = Path(__file__).resolve().parents[2]

    assert not (backend_dir / "config.py").exists()
    assert Config.BASE_DIR == backend_dir


def test_config_init_creates_nested_data_directories(tmp_path: Path) -> None:
    class IsolatedConfig(Config):
        DATA_DIR = tmp_path / "missing" / "data"
        PROJECTS_DIR = DATA_DIR / "projects"
        TEMP_DIR = DATA_DIR / "temp"

    app = Flask(__name__)

    IsolatedConfig.init_app(app)

    assert IsolatedConfig.PROJECTS_DIR.is_dir()
    assert IsolatedConfig.TEMP_DIR.is_dir()


def test_app_factory_uses_runtime_config() -> None:
    from app import create_app

    app = create_app("testing")

    assert app.config["API_PREFIX"] == "/api/v1"
    assert app.config["APP_NAME"] == "NoobBook"
    assert app.config["PROJECTS_DIR"] == app.config["DATA_DIR"] / "projects"
    assert app.config["TEMP_DIR"] == app.config["DATA_DIR"] / "temp"
