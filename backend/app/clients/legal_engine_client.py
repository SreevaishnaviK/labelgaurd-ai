"""Client for the Legal Engine evaluation service.

The backend builds the evaluation input from persisted extraction/OCR data
and sends structured fields only — never images. Failures surface as typed
exceptions; no evaluation results are ever fabricated on failure.
"""
from dataclasses import dataclass, field

import httpx

from app.config import get_settings


class LegalEngineError(Exception):
    """Legal engine could not be reached, timed out, or failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class LegalEvaluationResult:
    rules_evaluated: int
    results: list[dict] = field(default_factory=list)


def evaluate(input_payload: dict) -> LegalEvaluationResult:
    """Send the evaluation input to the legal engine and return rule results."""
    settings = get_settings()
    url = f"{settings.legal_engine_url}/api/v1/evaluate"
    try:
        response = httpx.post(url, json=input_payload, timeout=settings.legal_engine_timeout_seconds)
    except httpx.TimeoutException as exc:
        raise LegalEngineError("Legal engine timed out.") from exc
    except httpx.HTTPError as exc:
        raise LegalEngineError("Legal engine is unavailable.") from exc

    if response.status_code != 200:
        raise LegalEngineError(f"Legal engine rejected the request ({response.status_code}).")

    body = response.json()
    if body.get("status") != "success":
        raise LegalEngineError("Legal engine returned a non-success status.")
    return LegalEvaluationResult(
        rules_evaluated=int(body.get("rules_evaluated", 0)), results=body.get("results", [])
    )
