"""Runtime configuration for the Flask app."""

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class RuntimeSettings(BaseSettings):
    app_name: str = "NoobBook"
    version: str = "1.0.0"
    secret_key: str = "dev-secret-key-change-in-production"
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="ALLOWED_ORIGINS",
    )
    max_content_length: int = 100 * 1024 * 1024
    api_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:5173", "http://localhost:3000"]


runtime_settings = RuntimeSettings()


class Config:
    """Base Flask configuration."""

    APP_NAME = runtime_settings.app_name
    VERSION = runtime_settings.version
    SECRET_KEY = runtime_settings.secret_key
    DEBUG = False
    TESTING = False
    CORS_ALLOWED_ORIGINS = runtime_settings.cors_allowed_origins
    BASE_DIR = BACKEND_DIR
    DATA_DIR = BASE_DIR / "data"
    PROJECTS_DIR = DATA_DIR / "projects"
    TEMP_DIR = DATA_DIR / "temp"
    MAX_CONTENT_LENGTH = runtime_settings.max_content_length
    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {
        "pdf",
        "txt",
        "md",
        "docx",
        "json",
        "png",
        "jpg",
        "jpeg",
    }
    API_PREFIX = runtime_settings.api_prefix

    @classmethod
    def init_app(cls, app: Any) -> None:
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.PROJECTS_DIR.mkdir(exist_ok=True)
        cls.TEMP_DIR.mkdir(exist_ok=True)
        app.config["SECRET_KEY"] = cls.SECRET_KEY
        app.config["CORS_ALLOWED_ORIGINS"] = list(dict.fromkeys(cls.CORS_ALLOWED_ORIGINS))
        logger.info("%s v%s initialized (debug=%s)", cls.APP_NAME, cls.VERSION, cls.DEBUG)


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = "INFO"

    @classmethod
    def init_app(cls, app: Any) -> None:
        secret_key = os.getenv("SECRET_KEY", "").strip()
        if not secret_key:
            raise ValueError("SECRET_KEY environment variable must be set in production")
        cls.SECRET_KEY = secret_key
        cls.CORS_ALLOWED_ORIGINS = RuntimeSettings().cors_allowed_origins
        super().init_app(app)


class TestingConfig(Config):
    TESTING = True
    LOG_LEVEL = "DEBUG"
    DATA_DIR = Config.BASE_DIR / "test_data"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
