"""Inspection service.

Owns the Phase 2 upload flow: validation → storage of the original → CV
orchestration → OCR persistence → status tracking. API routes stay thin;
all database access lives here.
"""
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clients import computer_vision_client
from app.clients.computer_vision_client import CVRejectionError, CVServiceError
from app.config import get_settings
from app.models.inspection import (
    Inspection,
    InspectionStatus,
    OCRBlock,
    OCRDocument,
    ProcessingStatus,
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}
_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"%PDF-")
SUPPORTED_MESSAGE = "Only PNG, JPG, JPEG and PDF files are supported."

# Sequential public IDs: LGA-2026-00001, LGA-2026-00002, ...
_ID_PATTERN = re.compile(r"^LGA-\d{4}-(\d{5})$")


def _fail(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_upload(file: UploadFile, data: bytes) -> tuple[str, str]:
    """Validate extension/MIME/content/size. Returns (document_type, mime)."""
    settings = get_settings()
    if len(data) == 0:
        raise _fail(400, "EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > settings.max_upload_size_bytes:
        raise _fail(413, "FILE_TOO_LARGE", f"File exceeds the {settings.max_upload_size_mb} MB limit.")

    filename = file.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_MIME_TYPES:
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)

    if not data.startswith(_MAGIC):
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)
    if extension == "pdf" and not data.startswith(b"%PDF-"):
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)

    document_type = "pdf" if extension == "pdf" else "image"
    return document_type, mime or "application/octet-stream"


def _next_inspection_id(session: Session) -> str:
    """Allocate the next sequential LGA-2026-##### ID from the database."""
    year = "2026"
    rows = session.execute(select(Inspection.inspection_id)).scalars().all()
    max_num = 0
    for value in rows:
        match = _ID_PATTERN.match(value or "")
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"LGA-{year}-{max_num + 1:05d}"


def _store_original(inspection_id: str, data: bytes, extension: str) -> tuple[Path, str, str]:
    """Write the original file under uploads/originals with a UUID name.

    Returns (absolute_path, stored_filename, relative_path).
    """
    settings = get_settings()
    original_dir = Path(settings.upload_dir) / "originals"
    original_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{inspection_id}_{uuid.uuid4().hex}.{extension}"
    path = original_dir / stored_filename
    # Defense in depth: the UUID name cannot traverse, but verify anyway.
    resolved = path.resolve()
    if not str(resolved).startswith(str(Path(settings.upload_dir).resolve())):
        raise _fail(500, "STORAGE_ERROR", "Could not store the uploaded file safely.")
    resolved.write_bytes(data)
    return resolved, stored_filename, f"{settings.upload_dir}/originals/{stored_filename}"


def create_inspection_from_upload(file: UploadFile, session: Session) -> Inspection:
    """Run the full upload flow and persist everything. Raises HTTPException on failure."""
    data = file.file.read()
    document_type, mime = _validate_upload(file, data)
    settings = get_settings()

    extension = (file.filename or "upload.bin").rsplit(".", 1)[-1].lower()
    inspection = Inspection(
        inspection_id="pending",
        status=InspectionStatus.UPLOADED,
        processing_status=ProcessingStatus.UPLOADED,
        original_filename=Path(file.filename or "upload").name,  # strip any path components
        mime_type=mime,
        document_type=document_type,
        page_count=0,
    )
    session.add(inspection)
    session.flush()
    inspection.inspection_id = _next_inspection_id(session)

    path, stored_filename, relative_path = _store_original(inspection.inspection_id, data, extension)
    inspection.stored_filename = stored_filename
    inspection.file_path = relative_path
    inspection.processing_status = ProcessingStatus.PROCESSING
    session.commit()

    # Orchestrate CV. Any CV failure is terminal for this inspection: record it.
    try:
        analysis = computer_vision_client.analyze_document(
            filename=inspection.original_filename or stored_filename,
            content=data,
            mime_type=mime,
        )
    except (CVServiceError, CVRejectionError) as exc:
        code = "CV_SERVICE_UNAVAILABLE" if isinstance(exc, CVServiceError) else exc.code
        message = exc.message
        inspection.processing_status = ProcessingStatus.FAILED
        session.commit()
        raise _fail(503, code, message) from exc

    try:
        for page in analysis.pages:
            session.add(
                OCRDocument(
                    inspection=inspection,
                    page_number=int(page["page_number"]),
                    width=int(page["width"]),
                    height=int(page["height"]),
                    full_text=page.get("full_text", ""),
                    processed_path=page.get("processed_image"),
                    warped=bool(page.get("warped", False)),
                )
            )
            for block in page.get("blocks", []):
                bbox = block["bbox"]
                session.add(
                    OCRBlock(
                        inspection=inspection,
                        page_number=int(page["page_number"]),
                        block_id=block["id"],
                        text=block["text"],
                        confidence=float(block["confidence"]),
                        x=int(bbox["x"]),
                        y=int(bbox["y"]),
                        width=int(bbox["width"]),
                        height=int(bbox["height"]),
                        line_number=int(block.get("line_number", 0)),
                        block_number=int(block.get("block_number", 0)),
                    )
                )
        inspection.page_count = len(analysis.pages)
        inspection.processing_status = ProcessingStatus.PROCESSED
        session.commit()
    except (KeyError, TypeError, ValueError, SQLAlchemyError) as exc:
        session.rollback()
        inspection.processing_status = ProcessingStatus.FAILED
        session.commit()
        path.unlink(missing_ok=True)  # cleanup on persistence failure
        raise _fail(502, "OCR_STORAGE_FAILURE", "Could not persist OCR results.") from exc

    return inspection


def get_inspection_by_public_id(session: Session, inspection_id: str) -> Inspection:
    """Fetch an inspection by public ID or raise 404."""
    inspection = session.execute(
        select(Inspection).where(Inspection.inspection_id == inspection_id)
    ).scalar_one_or_none()
    if inspection is None:
        raise _fail(404, "INSPECTION_NOT_FOUND", "No inspection exists with that ID.")
    return inspection


def average_confidence(session: Session, inspection_id: int) -> float:
    """Average OCR block confidence for an inspection, from the database."""
    value = session.execute(
        select(func.avg(OCRBlock.confidence)).where(OCRBlock.inspection_id == inspection_id)
    ).scalar()
    return round(float(value), 1) if value is not None else 0.0
