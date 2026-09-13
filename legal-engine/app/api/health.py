"""Legal Engine API routes."""
from fastapi import APIRouter

from app.schemas.compliance import PlaceholderResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "LabelGuard AI Legal Engine"}


@router.post("/api/v1/evaluate", response_model=PlaceholderResponse)
def evaluate() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="not_implemented",
        message="Compliance rule evaluation will be implemented in Phase 5.",
    )
