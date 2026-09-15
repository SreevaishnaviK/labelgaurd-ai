"""Client for the AI extraction service.

The backend sends stored OCR output (never images) and receives structured
fields with evidence references. Failures surface as typed exceptions mapped
to stored failure states; no fabricated fields are ever returned.

Phase 4: the extraction mode is passed through (deterministic | ai_assisted |
auto — the AI service owns the policy), and the response's provider name is
surfaced for provenance/status display.
"""
from dataclasses import dataclass, field

import httpx

from app.config import get_settings


class AIServiceError(Exception):
    """AI service could not be reached or timed out."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class AIExtractionResult:
    status: str
    fields: list[dict] = field(default_factory=list)
    provider: str = "none"


def extract_fields(
    *, inspection_id: str, pages: list[dict], mode: str | None = None
) -> AIExtractionResult:
    """Send OCR pages to the AI service and return structured fields."""
    settings = get_settings()
    url = f"{settings.ai_service_url}/api/v1/extract"
    payload: dict = {"inspection_id": inspection_id, "pages": pages, "mode": mode or settings.extraction_mode}
    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=settings.ai_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise AIServiceError("AI service timed out.") from exc
    except httpx.HTTPError as exc:
        raise AIServiceError("AI service is unavailable.") from exc

    if response.status_code != 200:
        raise AIServiceError(f"AI service rejected the request ({response.status_code}).")

    body = response.json()
    if body.get("status") != "success":
        raise AIServiceError("AI service returned a non-success status.")
    return AIExtractionResult(
        status=body["status"], fields=body.get("fields", []), provider=body.get("provider", "none")
    )
