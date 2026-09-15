"""AI provider abstraction.

A provider turns OCR + deterministic candidates into AI-interpreted fields.
All provider-specific details (HTTP, auth, payload formats) stay inside the
provider module; the rest of the service only sees BaseAIProvider.

Providers NEVER make legal/compliance judgments — their contract is fields
with evidence references, validated against AIExtractionOut by the caller.
"""
from abc import ABC, abstractmethod

from app.schemas.extraction import AIExtractionOut, CandidateField, ExtractRequest


class AIProviderError(Exception):
    """Provider could not be reached, timed out, or returned unusable output."""


class BaseAIProvider(ABC):
    """Contract: OCR + deterministic candidates in, structured fields out."""

    name: str = "base"

    @abstractmethod
    def extract_fields(
        self, request: ExtractRequest, candidates: list[CandidateField]
    ) -> AIExtractionOut:
        """Interpret the OCR + candidates and return AI fields.

        Implementations must raise AIProviderError on any failure (transport,
        auth, timeout, malformed output) — the orchestrator then falls back
        to deterministic extraction. The caller re-validates the returned
        payload against the strict schema and evidence rules.
        """
