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
    # Which OCR pass produced this block ("A" base pipeline; "B"/"C" =
    # Phase 9B recovery). Optional: pre-9B blocks have none.
    source_pass: str | None = None


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

    # Persisted row id — the reference officers verify against (Phase 8).
    extracted_field_id: int
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


class RuleEvidenceOut(BaseModel):
    """Reference from a rule result to its supporting data (never duplicated
    OCR content — block ids and field references only)."""

    evidence_type: str
    evidence_reference: str | None = None
    ocr_block_id: str | None = None
    page_number: int | None = None
    extracted_field_id: int | None = None
    source_page: int | None = None


class RuleResultOut(BaseModel):
    """One rule's automated, immutable evaluation result."""

    rule_evaluation_id: int
    rule_id: str
    rule_number: str
    rule_title: str
    status: str
    severity: str
    finding: str
    required_information: list[str] = []
    actual_information: dict = {}
    confidence: float | None = None
    requires_officer_verification: bool = False
    source: dict = {}
    evidence: list[RuleEvidenceOut] = []
    # Phase 8: layered beside the automated result, never replacing it.
    effective_status: str | None = None
    officer_verification: dict | None = None


class EvaluationOut(BaseModel):
    """One persisted automated evaluation (the latest or requested version)."""

    inspection_id: str
    evaluation_id: int
    evaluation_version: int
    engine_version: str
    overall_status: str
    evaluated_at: datetime
    results: list[RuleResultOut]
    # Phase 8: backend-derived effective rollup + whether any rule still
    # awaits officer verification. None when no verification layer ran.
    officer_effective_status: str | None = None
    verification_required: bool | None = None


class VisualEvidenceOut(BaseModel):
    """One persisted visual measurement (Phase 7). Pixel values stay pixels;
    physical units appear only when a real calibration produced them."""

    evidence_id: str
    evidence_type: str
    page_number: int
    bbox: dict | None = None
    value: float | str | None = None
    unit: str | None = None
    confidence: float | None = None
    method: str
    verification_status: str
    ocr_block_id: str | None = None
    ocr_block_ids: list[str] = []
    field_name: str | None = None
    note: str | None = None


class InspectionOut(BaseModel):
    inspection_id: str
    status: str
    created_at: datetime
    file: FileMeta
    ocr: OCRRetrieval
    extraction: ExtractionOut
    # Latest automated evaluation, when one has been run.
    evaluation: EvaluationOut | None = None
    # Persisted visual measurements, when evidence analysis has been run.
    visual_evidence: list[VisualEvidenceOut] = []
    # Phase 8: officer verifications of fields (rules' verifications ride on
    # the evaluation payload; these are the field-level records).
    field_verifications: list["FieldVerificationOut"] = []


class OfficerVerificationIn(BaseModel):
    """Create one officer verification of an immutable rule evaluation."""

    rule_evaluation_id: int
    decision: str
    comment: str | None = None
    evidence_ocr_block_id: str | None = None
    evidence_visual_evidence_id: str | None = None
    evidence_extracted_field_id: int | None = None


class OfficerVerificationOut(BaseModel):
    id: int
    inspection_id: str
    evaluation_id: int
    rule_evaluation_id: int
    decision: str
    comment: str | None = None
    officer_identifier: str
    evidence_ocr_block_id: str | None = None
    evidence_visual_evidence_id: str | None = None
    evidence_extracted_field_id: int | None = None
    created_at: datetime


class FieldVerificationIn(BaseModel):
    """Create one officer verification of an extracted field."""

    extracted_field_id: int
    verification_status: str
    verified_value: dict | None = None
    comment: str | None = None
    evidence_ocr_block_id: str | None = None
    evidence_visual_evidence_id: str | None = None


class FieldVerificationOut(BaseModel):
    id: int
    extracted_field_id: int
    field_name: str
    verification_status: str
    verified_value: dict | None = None
    comment: str | None = None
    officer_identifier: str
    evidence_ocr_block_id: str | None = None
    evidence_visual_evidence_id: str | None = None
    created_at: datetime


class AuditLogOut(BaseModel):
    """One append-only audit entry."""

    id: int
    inspection_id: str
    action: str
    actor: str
    evaluation_id: int | None = None
    rule_evaluation_id: int | None = None
    decision: str | None = None
    previous_state: str | None = None
    comment: str | None = None
    timestamp: datetime


# --- Phase 9: history, dashboard, evaluation versions, reports ---


class InspectionSummaryOut(BaseModel):
    """One history row. Summaries only — never OCR payloads."""

    inspection_id: str
    product_name: str | None = None
    inspection_date: datetime
    automated_status: str | None = None
    officer_verified_status: str | None = None
    effective_status: str | None = None
    evaluation_version: int | None = None
    verification_required: bool = False
    has_evaluation: bool = False
    created_at: datetime
    updated_at: datetime


class InspectionHistoryOut(BaseModel):
    items: list[InspectionSummaryOut]
    page: int
    page_size: int
    total: int
    pages: int


class DashboardMetricsOut(BaseModel):
    """Database-backed overview. `automated` and `officer_effective` are
    reported side by side — officer data never silently replaces automated
    statistics."""

    total_inspections: int
    automated: dict[str, int]
    officer_effective: dict[str, int]
    recent_inspections: list[dict]


class EvaluationVersionOut(BaseModel):
    """One immutable evaluation version in the inspection's history."""

    evaluation_id: int
    evaluation_version: int
    engine_version: str
    overall_status: str
    created_at: datetime
    has_officer_verification: bool


class ReportOut(BaseModel):
    """Report metadata. `report_hash` is a file-integrity SHA-256 — it is NOT
    a digital signature."""

    id: int
    inspection_id: str
    evaluation_id: int
    evaluation_version: int
    report_hash: str
    storage_reference: str
    generated_at: datetime


class UploadErrorResponse(BaseModel):
    detail: dict
