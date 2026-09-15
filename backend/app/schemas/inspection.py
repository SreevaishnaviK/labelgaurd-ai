"""Inspection API schemas."""
from datetime import datetime

from pydantic import BaseModel


class BBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class OCRBlockOut(BaseModel):
    block_id: str
    page_number: int
    text: str
    confidence: float
    bbox: BBox
    line_number: int
    block_number: int


class OCRPageOut(BaseModel):
    page_number: int
    width: int
    height: int
    full_text: str
    # Processed (OCR-ready) page image relative to the backend's UPLOAD_DIR.
    processed_path: str | None = None
    # True when perspective correction changed geometry; original-image
    # coordinates are then invalid for this page.
    warped: bool = False


class UploadSuccess(BaseModel):
    inspection_id: str
    status: str
    filename: str
    document_type: str
    pages: int
    text_length: int
    blocks_detected: int


class UploadFailure(BaseModel):
    status: str
    inspection_id: str
    error: dict


class FileMeta(BaseModel):
    original_filename: str
    document_type: str


class OCRRetrieval(BaseModel):
    pages: list[OCRPageOut]
    blocks: list[OCRBlockOut]
    full_text: str
    blocks_detected: int
    average_confidence: float


class ExtractionEvidenceOut(BaseModel):
    """Reference to existing OCR blocks — no coordinate duplication."""

    ocr_block_id: str
    page_number: int


class FieldCandidateOut(BaseModel):
    """One plausible reading of an ambiguous/conflicted field, with provenance."""

    raw_text: str | None = None
    value: dict | None = None
    method: str = "deterministic"
    confidence: float | None = None
    evidence: list[ExtractionEvidenceOut] = []


class ExtractedFieldOut(BaseModel):
    """One structured field: extraction result, never a legal judgment."""

    field_name: str
    status: str
    value: dict | None = None
    raw_text: str | None = None
    ocr_confidence: float | None = None
    extraction_confidence: float | None = None
    # Phase 4 provenance.
    ai_confidence: float | None = None
    resolution_status: str | None = None
    method: str
    evidence: list[ExtractionEvidenceOut] = []
    candidates: list[FieldCandidateOut] | None = None


class ExtractionOut(BaseModel):
    fields: list[ExtractedFieldOut]


class InspectionOut(BaseModel):
    inspection_id: str
    status: str
    created_at: datetime
    file: FileMeta
    ocr: OCRRetrieval
    extraction: ExtractionOut


class UploadErrorResponse(BaseModel):
    detail: dict
