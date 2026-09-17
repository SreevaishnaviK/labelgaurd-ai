"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://labelguard:password@localhost:5432/labelguard"

    # CORS (comma-separated origins)
    cors_origins: str = "http://localhost:5173"

    # Internal services (Docker service names by default)
    cv_service_url: str = "http://localhost:8001"
    ai_service_url: str = "http://localhost:8002"
    legal_engine_url: str = "http://localhost:8003"

    # Uploads
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 20
    cv_timeout_seconds: int = 60

    # Legal engine evaluation
    legal_engine_timeout_seconds: int = 30

    # AI extraction
    ai_enabled: bool = True
    ai_timeout_seconds: int = 60
    # Mode sent to the AI service: deterministic | ai_assisted | auto.
    # The AI service owns the gating policy; the backend only chooses whether
    # AI-assisted extraction is requested at all.
    extraction_mode: str = "auto"

    # Development-only officer identity (Phase 8). Authentication and RBAC are
    # deferred — this is a documented placeholder, NOT secure authentication.
    officer_identifier: str = "officer-dev"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
