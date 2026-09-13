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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
