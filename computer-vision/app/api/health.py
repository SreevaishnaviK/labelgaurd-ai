"""Computer Vision service API routes."""
from fastapi import APIRouter

from app.schemas.vision import PlaceholderResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "LabelGuard AI Computer Vision"}


@router.post("/api/v1/analyze", response_model=PlaceholderResponse)
def analyze() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="not_implemented",
        message="Computer vision processing will be implemented in Phase 2.",
    )
