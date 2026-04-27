"""Runtime config tests for the NBB-902 Pydantic settings move."""

from pathlib import Path

from app.config.runtime import Config, RuntimeSettings


def test_runtime_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    settings = RuntimeSettings(_env_file=tmp_path / "missing.env")

    assert settings.app_name == "NoobBook"
    assert settings.api_prefix == "/api/v1"
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]


def test_runtime_settings_env_override(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALLOWED_ORIGINS=http://example.test,http://localhost:9999\n"
        "MAX_CONTENT_LENGTH=123\n",
        encoding="utf-8",
    )

    settings = RuntimeSettings(_env_file=env_file)

    assert settings.cors_allowed_origins == [
        "http://example.test",
        "http://localhost:9999",
    ]
    assert settings.max_content_length == 123


def test_backend_config_module_collision_is_removed() -> None:
    backend_dir = Path(__file__).resolve().parents[2]

    assert not (backend_dir / "config.py").exists()
    assert Config.BASE_DIR == backend_dir


def test_app_factory_uses_runtime_config() -> None:
    from app import create_app

    app = create_app("testing")

    assert app.config["API_PREFIX"] == "/api/v1"
    assert app.config["APP_NAME"] == "NoobBook"
