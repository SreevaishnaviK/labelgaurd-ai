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

    # --- Phase 4: AI-assisted extraction ---------------------------------
    # none: deterministic only (no API key required). mock: scripted provider
    # for tests/demos. openai: real provider; all OpenAI specifics stay in
    # providers/openai_provider.py.
    ai_provider: str = "none"
    # Deterministic results at or above this confidence are authoritative and
    # never sent to the AI in auto mode.
    ai_min_deterministic_confidence: float = 85.0

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 20.0
    # Overridable so integration tests can point at a local stub.
    openai_base_url: str = "https://api.openai.com/v1"

    # Mock provider demo script: a JSON array of AIFieldOut objects the mock
    # returns for every call. Lets offline demos exercise the full
    # AI-assisted pipeline (including fallbacks) without any API key.
    mock_ai_fields: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
