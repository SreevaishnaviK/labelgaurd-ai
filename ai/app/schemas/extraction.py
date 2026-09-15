"""AI service schemas: OCR in, structured fields out.

The AI service receives OCR output (never images) and returns structured
fields with evidence references back to OCR block IDs. Extraction is not a
legal judgment: statuses are detected/not_detected/ambiguous only.

Phase 4 adds the AI-assisted layer: a strict schema (AIFieldOut) for what an
LLM provider may return, extraction modes, and provenance on every field
(method + resolution_status + separate confidences).
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

FieldStatus = Literal["detected", "not_detected", "ambiguous"]
ExtractionMethod = Literal["deterministic", "ai_assisted", "deterministic_fallback"]
ExtractionMode = Literal["deterministic", "ai_assisted", "auto"]


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


class EvidenceRef(BaseModel):
    """Reference to existing OCR evidence — no coordinate duplication."""

    ocr_block_id: str
    page_number: int


class CandidateReading(BaseModel):
    """One current candidate value for a field, with its provenance."""

    raw_text: str | None = None
    value: dict[str, Any] | None = None
    method: ExtractionMethod = "deterministic"
    confidence: float | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class CandidateField(BaseModel):
    """A deterministic result offered to the AI for interpretation."""

    field_name: str
    status: FieldStatus
    value: dict[str, Any] | None = None
    extraction_confidence: float | None = None
    readings: list[CandidateReading] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    inspection_id: str
    pages: list[OCRPageIn]
    # auto: deterministic first, AI only where useful; deterministic: rules
    # only; ai_assisted: AI reviews every field. AI never makes legal calls.
    mode: ExtractionMode = "auto"


class AIFieldOut(BaseModel):
    """Strict contract for one field returned by an AI provider.

    Providers returning anything that does not validate against this schema
    are rejected wholesale and the pipeline falls back to deterministic.
    """

    field_name: str
    status: FieldStatus
    value: dict[str, Any] | str | None = None
    raw_text: str | None = None
    confidence: float = Field(ge=0, le=100)
    evidence_block_ids: list[str] = Field(default_factory=list)


class AIExtractionOut(BaseModel):
    """The exact JSON shape an AI provider must return."""

    fields: list[AIFieldOut] = Field(default_factory=list)


class FieldCandidate(BaseModel):
    """One plausible reading of an ambiguous field, with provenance."""

    raw_text: str | None = None
    value: dict[str, Any] | None = None
    method: ExtractionMethod = "deterministic"
    confidence: float | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ExtractedFieldOut(BaseModel):
    field_name: str
    status: FieldStatus
    value: dict[str, Any] | None = None
    raw_text: str | None = None
    ocr_confidence: float | None = None
    extraction_confidence: float | None = None
    ai_confidence: float | None = None
    method: ExtractionMethod = "deterministic"
    # deterministic | ai_resolved | ai_confirmed | conflict | ai_unavailable
    resolution_status: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    candidates: list[FieldCandidate] | None = None


class ExtractSuccess(BaseModel):
    status: Literal["success"]
    inspection_id: str
    provider: str = "none"
    mode: ExtractionMode = "auto"
    fields: list[ExtractedFieldOut]


class HealthOut(BaseModel):
    status: str
    service: str
    # Provider name only — never keys or endpoints with credentials.
    provider: str = "none"
