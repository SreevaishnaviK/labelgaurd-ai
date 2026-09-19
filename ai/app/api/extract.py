"""Extraction API endpoint."""

from fastapi import APIRouter

from app.extraction.orchestrator import run_extraction
from app.schemas.extraction import ExtractRequest, ExtractSuccess


router = APIRouter(prefix="/api/v1", tags=["extraction"])


@router.post("/extract", response_model=ExtractSuccess)
def extract(request: ExtractRequest) -> ExtractSuccess:
    """Run deterministic/AI-assisted structured field extraction."""
    return run_extraction(request)