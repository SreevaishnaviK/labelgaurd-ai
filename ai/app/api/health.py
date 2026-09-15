"""AI service API routes.

POST /api/v1/extract — structured field extraction over OCR output; never a
legal judgment. Phase 4 adds extraction modes: "auto" (deterministic first,
AI only where useful), "deterministic" (rules only), "ai_assisted" (AI
reviews every field). GET /health exposes the provider NAME only — never
keys or endpoints carrying credentials.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.extraction.orchestrator import run_extraction
from app.schemas.extraction import ExtractRequest, ExtractSuccess, HealthOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        service="LabelGuard AI AI Service",
        provider=get_settings().ai_provider,
    )


@router.post("/api/v1/extract")
def extract(request: ExtractRequest) -> ExtractSuccess:
    if not request.pages:
        raise HTTPException(
            status_code=422,
            detail={"code": "NO_PAGES", "message": "At least one OCR page is required."},
        )
    try:
        return run_extraction(request)
    except ValueError as exc:
        # Extractor misconfiguration; AI provider failures never reach here.
        raise HTTPException(
            status_code=500,
            detail={"code": "EXTRACTOR_UNAVAILABLE", "message": str(exc)},
        ) from exc
