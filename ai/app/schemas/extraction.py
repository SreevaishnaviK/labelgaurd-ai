"""AI service schemas: OCR in, structured fields out.

The AI service receives OCR output (never images) and returns structured
fields with evidence references back to OCR block IDs. Extraction is not a
legal judgment: statuses are detected/not_detected/ambiguous only.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

FieldStatus = Literal["detected", "not_detected", "ambiguous"]
ExtractionMethod = Literal["deterministic"]


class OCRBlockIn(BaseModel):
    id: str
    text: str
    confidence: float = Field(ge=0, le=100)
    page_number: int = 1
    bbox: dict[str, int] = Field(default_factory=dict)


class OCRPageIn(BaseModel):
    page_number: int
    width: int
    height: int
    full_text: str = ""
    blocks: list[OCRBlockIn] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    inspection_id: str
    pages: list[OCRPageIn]


class EvidenceRef(BaseModel):
    """Reference to existing OCR evidence — no coordinate duplication."""

    ocr_block_id: str
    page_number: int


class FieldCandidate(BaseModel):
    """One plausible reading of an ambiguous field."""

    raw_text: str
    value: dict[str, Any]


class ExtractedFieldOut(BaseModel):
    field_name: str
    status: FieldStatus
    value: dict[str, Any] | None = None
    raw_text: str | None = None
    ocr_confidence: float | None = None
    extraction_confidence: float | None = None
    method: ExtractionMethod = "deterministic"
    evidence: list[EvidenceRef] = Field(default_factory=list)
    candidates: list[FieldCandidate] | None = None


class ExtractSuccess(BaseModel):
    status: Literal["success"]
    inspection_id: str
    fields: list[ExtractedFieldOut]


class HealthOut(BaseModel):
    status: str
    service: str
