"""Scripted mock provider for tests and offline demos.

Returns controlled structured JSON — automated tests and demos never touch a
real external API. Scripting comes from two places:
- configure(): per-call script used by unit tests;
- MOCK_AI_FIELDS (JSON array): a static script for Docker/offline demos.
With no script it contributes no fields, so the merged output is exactly the
deterministic result (a valid, honest mode).
"""
import json
import logging

from pydantic import ValidationError

from app.providers.base import AIProviderError, BaseAIProvider
from app.schemas.extraction import AIExtractionOut, AIFieldOut, CandidateField, ExtractRequest

logger = logging.getLogger(__name__)


class MockAIProvider(BaseAIProvider):
    name = "mock"

    def __init__(self, static_fields_json: str = "") -> None:
        self._script: AIExtractionOut | Exception | None = None
        self._static = self._parse_static(static_fields_json)

    @staticmethod
    def _parse_static(static_fields_json: str) -> AIExtractionOut:
        """A malformed MOCK_AI_FIELDS is a provider failure, not a crash — the
        orchestrator degrades to deterministic exactly like a bad LLM reply."""
        if not static_fields_json.strip():
            return AIExtractionOut(fields=[])
        try:
            return AIExtractionOut.model_validate(json.loads(static_fields_json))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AIProviderError(f"MOCK_AI_FIELDS is not a valid AI payload: {exc}") from exc

    def configure(
        self,
        fields: list[AIFieldOut] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Script the next response: either fields or an error to raise."""
        self._script = error if error is not None else AIExtractionOut(fields=fields or [])

    def extract_fields(
        self, request: ExtractRequest, candidates: list[CandidateField]
    ) -> AIExtractionOut:
        script, self._script = self._script, None
        if isinstance(script, Exception):
            raise script
        if script is None:
            script = self._static
        if script is None or not script.fields:
            logger.info("MockAIProvider has no scripted response; contributing nothing.")
            return AIExtractionOut(fields=[])
        return script
