"""Provider registry: configuration selects the implementation.

AI_PROVIDER=none → None (deterministic-only mode, no API key required).
Unknown providers also degrade to None with a warning: a configuration
typo must never fail an inspection.
"""
import logging

from app.config import get_settings
from app.providers.base import BaseAIProvider
from app.providers.mock_provider import MockAIProvider
from app.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[BaseAIProvider]] = {
    "mock": MockAIProvider,
    "openai": OpenAIProvider,
}


def get_ai_provider() -> BaseAIProvider | None:
    settings = get_settings()
    name = settings.ai_provider
    if name == "none":
        return None
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        logger.warning("Unknown AI_PROVIDER=%r; running deterministic-only.", name)
        return None
    if provider_cls is MockAIProvider:
        return MockAIProvider(static_fields_json=settings.mock_ai_fields)
    return provider_cls()
