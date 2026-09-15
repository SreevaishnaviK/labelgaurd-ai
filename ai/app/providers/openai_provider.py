"""OpenAI provider: all OpenAI-specific code lives here.

Reads credentials/model from Settings (environment variables only — never
hardcoded, never logged, never exposed to other services or the frontend).
Responses are parsed as strict JSON and validated against AIExtractionOut;
any transport, parse, or validation failure becomes AIProviderError so the
pipeline falls back to deterministic extraction.
"""
import json
import logging

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.prompts.extraction_system import EXTRACTION_SYSTEM_PROMPT
from app.prompts.extraction_user import build_user_prompt
from app.providers.base import AIProviderError, BaseAIProvider
from app.schemas.extraction import AIExtractionOut, CandidateField, ExtractRequest

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model
        self._timeout = settings.openai_timeout_seconds
        self._base_url = settings.openai_base_url.rstrip("/")

    def extract_fields(
        self, request: ExtractRequest, candidates: list[CandidateField]
    ) -> AIExtractionOut:
        if not self._api_key:
            raise AIProviderError("OPENAI_API_KEY is not configured.")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request, candidates)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AIProviderError("OpenAI request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            # Status code only — never the request headers or the API key.
            raise AIProviderError(f"OpenAI rejected the request ({exc.response.status_code}).") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("OpenAI is unreachable.") from exc

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("OpenAI returned an unexpected completion shape.") from exc
        return self._parse(content)

    @staticmethod
    def _parse(content: str) -> AIExtractionOut:
        """Strict JSON contract: anything unparseable is a provider failure."""
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AIProviderError("OpenAI returned non-JSON output.") from exc
        try:
            return AIExtractionOut.model_validate(data)
        except ValidationError as exc:
            raise AIProviderError("OpenAI output failed schema validation.") from exc
