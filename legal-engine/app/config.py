"""Legal Engine configuration."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_port: int = 8003
    # Version stamped into persisted evaluations for provenance (rule logic
    # changes bump this; historical evaluations keep the version that ran).
    engine_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
