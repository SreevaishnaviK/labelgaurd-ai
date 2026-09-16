"""Database models (Phase 1 foundation, Phase 2 OCR, Phase 3+4 extraction,
Phase 6 evaluation)."""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InspectionStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ProcessingStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


def _enum_values(enum_cls):
    """Store enum VALUES (lowercase labels the migrations create), not NAMES."""
    return [member.value for member in enum_cls]


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(
            InspectionStatus,
            name="inspection_status",
            values_callable=_enum_values,
        ),
        default=InspectionStatus.UPLOADED,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Phase 2: uploaded file metadata
    original_filename: Mapped[str | None] = mapped_column(String(512))
    stored_filename: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(1024))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    document_type: Mapped[str | None] = mapped_column(String(32))
    page_count: Mapped[int | None] = mapped_column(default=0)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            values_callable=_enum_values,
        ),
        default=ProcessingStatus.UPLOADED,
    )

    product: Mapped["Product | None"] = relationship(back_populates="inspection", uselist=False)
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="inspection")
    ocr_documents: Mapped[list["OCRDocument"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )
    ocr_blocks: Mapped[list["OCRBlock"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["InspectionEvaluation"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(512))
    manufacturer: Mapped[str | None] = mapped_column(String(512))
    net_quantity: Mapped[str | None] = mapped_column(String(128))
    mrp: Mapped[float | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    inspection: Mapped[Inspection] = relationship(back_populates="product")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(255))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inspection: Mapped[Inspection] = relationship(back_populates="audit_logs")


class OCRDocument(Base):
    """One row per OCR'd page of an inspection's document."""

    __tablename__ = "ocr_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    full_text: Mapped[str] = mapped_column(Text, default="")
    # Processed (OCR-ready) page image, stored by the CV service under
    # UPLOAD_DIR/processed/... (shared volume in Docker). Null when unavailable.
    processed_path: Mapped[str | None] = mapped_column(String(1024))
    # True when perspective correction changed geometry — original-image
    # coordinates are then invalid for this page.
    warped: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inspection: Mapped[Inspection] = relationship(back_populates="ocr_documents")


class ExtractedField(Base):
    """One structured field extracted from an inspection's OCR (Phase 3+4)."""

    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # detected/not_detected/ambiguous
    value_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Ambiguous/conflicted fields keep every candidate so review UIs survive refresh.
    candidates_json: Mapped[list | None] = mapped_column(JSON, default=None)
    raw_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    # Phase 4 provenance: ai_confidence is the AI provider's own confidence
    # (None for pure deterministic fields); resolution_status records how the
    # final value was settled (ai_resolved | ai_confirmed | conflict |
    # ai_unavailable). Competing readings live in ExtractionCandidate rows.
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    resolution_status: Mapped[str | None] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    inspection: Mapped[Inspection] = relationship(back_populates="extracted_fields")
    evidence: Mapped[list["ExtractedFieldEvidence"]] = relationship(
        back_populates="extracted_field", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["ExtractionCandidate"]] = relationship(
        back_populates="extracted_field", cascade="all, delete-orphan"
    )


class ExtractedFieldEvidence(Base):
    """Link from an extracted field back to its supporting OCR block."""

    __tablename__ = "extracted_field_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    extracted_field_id: Mapped[int] = mapped_column(
        ForeignKey("extracted_fields.id"), nullable=False, index=True
    )
    ocr_block_id: Mapped[str] = mapped_column(String(32), nullable=False)
    page_number: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    extracted_field: Mapped[ExtractedField] = relationship(back_populates="evidence")


class ExtractionCandidate(Base):
    """One competing reading of an extracted field (Phase 4 auditability).

    Preserves deterministic vs AI-assisted candidates side by side — the
    merger never silently discards a reading, so review UIs can show exactly
    what each method proposed, with its own evidence links.
    """

    __tablename__ = "extraction_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    extracted_field_id: Mapped[int] = mapped_column(
        ForeignKey("extracted_fields.id"), nullable=False, index=True
    )
    value_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    raw_text: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    # OCR block references backing THIS reading (never duplicated coordinates).
    evidence_json: Mapped[list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    extracted_field: Mapped[ExtractedField] = relationship(back_populates="candidates")


class OCRBlock(Base):
    """One OCR text block with pixel bounding box on its page."""

    __tablename__ = "ocr_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    block_id: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    x: Mapped[int] = mapped_column(nullable=False)
    y: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    block_number: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inspection: Mapped[Inspection] = relationship(back_populates="ocr_blocks")


class InspectionEvaluation(Base):
    """One automated compliance evaluation run over an inspection (Phase 6).

    Records are immutable: re-evaluation appends a new row with a bumped
    evaluation_version — earlier evaluations are never updated or deleted,
    so the historical automated result is always preserved. Retrieval shows
    the latest version; officer corrections (later phase) must be stored
    separately, never spliced into these records.
    """

    __tablename__ = "inspection_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("inspections.id"), nullable=False, index=True
    )
    evaluation_version: Mapped[int] = mapped_column(nullable=False, default=1)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # Backend-derived rollup: COMPLIANT | NON_COMPLIANT | REVIEW_REQUIRED |
    # INCOMPLETE. Not a score, not a certification — see overall_status().
    overall_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inspection: Mapped[Inspection] = relationship(back_populates="evaluations")
    rule_results: Mapped[list["RuleEvaluation"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class RuleEvaluation(Base):
    """One rule's automated result within an evaluation (immutable)."""

    __tablename__ = "rule_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_evaluations.id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_number: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    finding: Mapped[str] = mapped_column(Text, nullable=False)
    required_information: Mapped[list | None] = mapped_column(JSON, default=None)
    actual_information: Mapped[dict | None] = mapped_column(JSON, default=None)
    # 0-1 as produced by the legal engine (None when the engine reports none).
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    requires_officer_verification: Mapped[bool] = mapped_column(default=False)
    source: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evaluation: Mapped[InspectionEvaluation] = relationship(back_populates="rule_results")
    evidence: Mapped[list["RuleEvaluationEvidence"]] = relationship(
        back_populates="rule_evaluation", cascade="all, delete-orphan"
    )


class RuleEvaluationEvidence(Base):
    """Reference from a rule result back to its supporting data.

    Stores references only — OCR block ids, extracted-field ids — never a
    duplicate of the underlying text or coordinates.
    """

    __tablename__ = "rule_evaluation_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("rule_evaluations.id"), nullable=False, index=True
    )
    # extracted_field | ocr_block | visual_measurement | schedule
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Human-readable reference (field name, measurement key, schedule name).
    evidence_reference: Mapped[str | None] = mapped_column(String(255))
    ocr_block_id: Mapped[str | None] = mapped_column(String(32))
    page_number: Mapped[int | None] = mapped_column()
    extracted_field_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_fields.id"), nullable=True
    )
    source_page: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rule_evaluation: Mapped[RuleEvaluation] = relationship(back_populates="evidence")
