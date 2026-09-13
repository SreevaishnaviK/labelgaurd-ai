"""Extractor resolution: config selects the implementation.

Adding an LLMFieldExtractor later is a registry entry + env var — the API
contract never changes.
"""
from app.config import get_settings
from app.extraction.base import BaseFieldExtractor
from app.extraction.deterministic import DeterministicFieldExtractor


def get_field_extractor() -> BaseFieldExtractor:
    name = get_settings().extractor
    extractors: dict[str, type[BaseFieldExtractor]] = {
        "deterministic": DeterministicFieldExtractor,
    }
    extractor_cls = extractors.get(name)
    if extractor_cls is None:
        raise ValueError(f"Unknown extractor: {name}")
    return extractor_cls()
