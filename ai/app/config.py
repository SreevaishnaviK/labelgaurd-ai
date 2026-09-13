"""AI service configuration."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_port: int = 8002

    # Field extractor implementation (deterministic today; LLM later).
    extractor: str = "deterministic"

    # Extraction-confidence floor for matches that clear all rule gates.
    extraction_confidence: float = 95.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
