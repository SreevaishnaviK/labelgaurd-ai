"""AI service API routes."""
from fastapi import APIRouter

from app.schemas.extraction import PlaceholderResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "LabelGuard AI AI Service"}


@router.post("/api/v1/extract", response_model=PlaceholderResponse)
def extract() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="not_implemented",
        message="AI extraction will be implemented in Phase 4.",
    )
