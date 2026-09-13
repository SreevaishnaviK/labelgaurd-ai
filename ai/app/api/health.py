"""AI service API routes."""
from fastapi import APIRouter, HTTPException

from app.extraction.extractor import get_field_extractor
from app.schemas.extraction import ExtractRequest, ExtractSuccess, HealthOut

router = APIRouter()


@router.get("/health")
def health() -> HealthOut:
    return HealthOut(status="ok", service="LabelGuard AI AI Service")


@router.post("/api/v1/extract")
def extract(request: ExtractRequest) -> ExtractSuccess:
    """Structured field extraction over OCR output — never a legal judgment."""
    if not request.pages:
        raise HTTPException(
            status_code=422,
            detail={"code": "NO_PAGES", "message": "At least one OCR page is required."},
        )
    try:
        extractor = get_field_extractor()
        fields = extractor.extract_fields(request.pages)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "EXTRACTOR_UNAVAILABLE", "message": str(exc)},
        ) from exc
    return ExtractSuccess(status="success", inspection_id=request.inspection_id, fields=fields)
