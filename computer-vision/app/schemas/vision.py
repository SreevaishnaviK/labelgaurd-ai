"""Computer Vision service schemas."""
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class OCRBlock(BaseModel):
    id: str
    text: str
    confidence: float = Field(ge=0, le=100)
    bbox: BoundingBox
    line_number: int
    block_number: int
    page_number: int
    # Which OCR pass produced this block ("A" = base pipeline, "B" =
    # contrast-recovery, "C" = upscaled-recovery). Optional so historical
    # payloads stay valid.
    source_pass: str | None = None


class OCRPage(BaseModel):
    page_number: int
    width: int
    height: int
    full_text: str
    blocks: list[OCRBlock]
    # Geometry of the processed page vs the original upload.
    processed_image: str
    warped: bool
    # Multi-pass recovery: passes that ran ("A" always; "B"/"C" when a
    # mandatory-declaration anchor was missing) and their bounded extra cost.
    ocr_passes: list[str] = Field(default_factory=lambda: ["A"])
    recovery_time_ms: int = 0


class AnalyzeMetadata(BaseModel):
    processing_time_ms: int


class AnalyzeSuccess(BaseModel):
    status: str
    document_type: str
    pages: list[OCRPage]
    metadata: AnalyzeMetadata


class EvidenceBoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class EvidencePage(BaseModel):
    """One page's persisted OCR data — the evidence pass never re-runs OCR."""

    page_number: int
    width: int
    height: int
    processed_path: str  # relative to the service's UPLOAD_DIR
    blocks: list[OCRBlock] = Field(default_factory=list)


class EvidenceFieldRef(BaseModel):
    """An extracted field's evidence references (block ids + pages)."""

    field_name: str
    evidence: list[dict] = Field(default_factory=list)  # {ocr_block_id, page_number}


class Calibration(BaseModel):
    """Optional physical scale. Never invented by the service itself."""

    px_per_mm: float = Field(gt=0)
    source: str  # what established the scale (documented provenance)


class EvidenceAnalyzeRequest(BaseModel):
    inspection_id: str
    pages: list[EvidencePage] = Field(min_length=1)
    fields: list[EvidenceFieldRef] = Field(default_factory=list)
    calibration: Calibration | None = None
    # Path of the unprocessed original upload (relative to UPLOAD_DIR), when
    # available — symbol detection needs color, which the binarized OCR image
    # no longer carries. Optional: without it symbol evidence is INSUFFICIENT.
    original_path: str | None = None


class EvidenceItem(BaseModel):
    """One measured/observed visual fact. Pixel values are never presented
    as physical measurements; physical values exist only with calibration."""

    evidence_id: str
    evidence_type: str  # PDP_AREA | TEXT_HEIGHT | DECLARATION_REGION | CONTRAST | READABILITY | BOUNDARY | PACKAGE_DIMENSION
    page_number: int
    bbox: EvidenceBoundingBox | None = None
    value: float | str | None = None
    unit: str | None = None
    confidence: float = Field(ge=0, le=1)
    method: str
    verification_status: str  # AUTOMATED | INSUFFICIENT_EVIDENCE
    ocr_block_id: str | None = None
    # Declaration regions carry every anchor block id + the field they came
    # from, so evidence stays traceable end to end.
    ocr_block_ids: list[str] = Field(default_factory=list)
    field_name: str | None = None
    note: str | None = None


class EvidenceAnalyzeSuccess(BaseModel):
    inspection_id: str
    evidence: list[EvidenceItem]


class AnalyzeErrorDetail(BaseModel):
    code: str
    message: str


class AnalyzeError(BaseModel):
    status: str
    error: AnalyzeErrorDetail
