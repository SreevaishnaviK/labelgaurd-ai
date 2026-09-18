"""Inspection service.

Owns the Phase 2 upload flow: validation → storage of the original → CV
orchestration → OCR persistence → status tracking. API routes stay thin;
all database access lives here.
"""
import logging
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.clients import ai_client, computer_vision_client
from app.clients.ai_client import AIServiceError
from app.clients.computer_vision_client import CVRejectionError, CVServiceError
from app.config import get_settings
from app.models.inspection import (
    ExtractionCandidate,
    ExtractedField,
    ExtractedFieldEvidence,
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


def _extraction_pages(inspection: Inspection, session: Session) -> list[dict]:
    """Build the AI service's OCR input from persisted rows (never the image)."""
    pages = []
    for doc in sorted(inspection.ocr_documents, key=lambda d: d.page_number):
        blocks = sorted(
            [b for b in inspection.ocr_blocks if b.page_number == doc.page_number],
            key=lambda b: b.id,
        )
        pages.append(
            {
                "page_number": doc.page_number,
                "width": doc.width,
                "height": doc.height,
                "full_text": doc.full_text or "",
                "blocks": [
                    {
                        "id": b.block_id,
                        "text": b.text,
                        "confidence": float(b.confidence),
                        "page_number": b.page_number,
                        "bbox": {"x": b.x, "y": b.y, "width": b.width, "height": b.height},
                        # Recovery-pass provenance; the AI schema treats it as
                        # optional so older rows (NULL) serialize as "A".
                        "source_pass": b.source_pass or "A",
                    }
                    for b in blocks
                ],
            }
        )
    return pages


def _validate_field_evidence(item: dict, block_texts: dict[str, str]) -> dict:
    """§19/§20 evidence-integrity gate over one AI-service field payload.

    A field may stay "detected" only when its evidence references exist on
    the CURRENT inspection and the referenced blocks textually support the
    value. Otherwise the field is downgraded to ambiguous — never silently
    deleted, so the officer sees that a candidate existed and failed
    validation. This is the last line of defense against cross-inspection
    leakage or hallucinated values; deterministic candidates that the AI
    service already validated are re-checked here at zero trust.
    """
    value = item.get("value")
    refs = item.get("evidence") or []
    if item.get("status") != "detected" or value is None:
        return item
    if not refs:
        return {**item, "status": "ambiguous", "resolution_status": "evidence_missing"}
    texts = [block_texts.get(ref.get("ocr_block_id"), "") for ref in refs]
    if any(not t for t in texts):
        return {**item, "status": "ambiguous", "resolution_status": "evidence_missing"}
    if not _value_supported(value, texts):
        return {**item, "status": "ambiguous", "resolution_status": "evidence_mismatch"}
    return item


def _value_supported(value: dict, texts: list[str]) -> bool:
    """True when the value's core content is derivable from the evidence text.
    Compares on compacted text (whitespace/punctuation-insensitive) so OCR
    spacing artifacts do not fail honest values."""
    def _compact(s: str) -> str:
        return re.sub(r"[^0-9a-z@.+-]", "", s.lower())

    corpus = _compact(" ".join(texts))

    def _present(fragment: str | None) -> bool:
        return bool(fragment) and _compact(fragment) in corpus

    if "name" in value:  # company / product names
        return _present(str(value["name"]))
    if "address" in value:
        # Address lines wrap; the PIN or city fragment anchors it.
        tail = str(value["address"]).split(",")[-1].strip()
        return _present(tail) or _present(str(value["address"])[:12])
    if "amount" in value:  # MRP — match the numeric amount
        return _present(f"{value['amount']:g}")
    if "value" in value and "unit" in value:  # net quantity
        return _present(f"{value['value']:g}")
    if "date" in value:
        return _present(str(value["date"]))
    if "batch" in value:
        return _present(str(value["batch"]))
    if "phone" in value:
        digits = re.sub(r"\D", "", str(value["phone"]))
        return bool(digits) and digits in re.sub(r"\D", "", corpus)
    if "email" in value:
        return _present(str(value["email"]))
    if "url" in value:
        return _present(str(value["url"]))
    if "ingredients" in value:
        first = str(value["ingredients"]).split(",")[0].strip()
        return _present(first)
    if "declaration" in value:
        return True  # visual-symbol fields carry CV bbox evidence, not OCR text
    if "contact" in value:
        return _present(str(value["contact"]))
    return True  # free-form shapes: presence of valid evidence refs suffices


def run_extraction(session: Session, inspection: Inspection) -> str:
    """Call the AI service over stored OCR and persist the structured fields.

    AI failures leave the inspection processed-without-extraction; nothing is
    fabricated. Re-extraction replaces previous fields (update path). Returns
    the AI service's provider name for system status ("none" when AI is off).
    """
    provider_name = "none"
    if get_settings().ai_enabled:
        try:
            result = ai_client.extract_fields(
                inspection_id=inspection.inspection_id,
                pages=_extraction_pages(inspection, session),
            )
        except AIServiceError as exc:
            logger.warning("AI extraction failed for %s: %s", inspection.inspection_id, exc.message)
            return provider_name
        provider_name = result.provider or "none"
        # §19/§20: every persisted field must be backed by evidence that
        # exists on THIS inspection and textually supports the value.
        block_texts = {b.block_id: b.text for b in inspection.ocr_blocks}
        for field in session.execute(
            select(ExtractedField).where(ExtractedField.inspection_id == inspection.id)
        ).scalars():
            session.delete(field)
        for item in result.fields:
            item = _validate_field_evidence(item, block_texts)
            field = ExtractedField(
                inspection=inspection,
                field_name=item["field_name"],
                status=item["status"],
                value_json=item.get("value"),
                raw_text=item.get("raw_text"),
                ocr_confidence=item.get("ocr_confidence"),
                extraction_confidence=item.get("extraction_confidence"),
                ai_confidence=item.get("ai_confidence"),
                resolution_status=item.get("resolution_status"),
                method=item.get("method", "deterministic"),
            )
            session.add(field)
            session.flush()  # assign field.id before evidence/candidate rows
            for ref in item.get("evidence", []):
                session.add(
                    ExtractedFieldEvidence(
                        extracted_field=field,
                        ocr_block_id=ref["ocr_block_id"],
                        page_number=ref.get("page_number", 1),
                    )
                )
            # Phase 4 auditability: every competing reading (deterministic vs
            # AI-assisted) is preserved with method + confidence + evidence.
            for candidate in item.get("candidates") or []:
                session.add(
                    ExtractionCandidate(
                        extracted_field=field,
                        value_json=candidate.get("value"),
                        raw_text=candidate.get("raw_text"),
                        method=candidate.get("method", "deterministic"),
                        confidence=candidate.get("confidence"),
                        evidence_json=candidate.get("evidence"),
                    )
                )
    return provider_name


def _candidate_outs(field: ExtractedField) -> list[dict]:
    """Candidate readings from the normalized table, falling back to legacy
    candidates_json rows written before migration 0005."""
    if field.candidates:
        return [
            {
                "raw_text": c.raw_text,
                "value": c.value_json,
                "method": c.method,
                "confidence": float(c.confidence) if c.confidence is not None else None,
                "evidence": c.evidence_json or [],
            }
            for c in field.candidates
        ]
    return [dict(c) for c in (field.candidates_json or [])]


def get_extracted_fields(session: Session, inspection: Inspection) -> list[ExtractedField]:
    """Persisted extraction for retrieval (empty list when none)."""
    return list(
        session.execute(
            select(ExtractedField)
            .where(ExtractedField.inspection_id == inspection.id)
            .order_by(ExtractedField.id)
        ).scalars()
    )


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
                        # "A" base pipeline, "B"/"C" recovery passes.
                        source_pass=block.get("source_pass"),
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

    # Phase 3: structured extraction over the stored OCR. AI outages do not
    # fail the upload — the inspection stays processed, extraction just empty.
    try:
        run_extraction(session, inspection)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("Extraction persistence failed for %s", inspection.inspection_id, exc_info=exc)

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
