"""Database models (Phase 1 foundation + Phase 2 OCR)."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
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
