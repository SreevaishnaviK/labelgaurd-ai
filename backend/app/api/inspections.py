"""Inspection API routes (Phase 2)."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.inspection import InspectionOut, OCRBlockOut, OCRPageOut, UploadSuccess
from app.services import inspection_service
from app.services.inspection_service import average_confidence

router = APIRouter(prefix="/api/v1/inspections")


@router.post("/upload", response_model=UploadSuccess)
def upload_inspection(file: UploadFile = File(...), session: Session = Depends(get_db)) -> UploadSuccess:
    inspection = inspection_service.create_inspection_from_upload(file, session)
    full_text = "\n\n".join(doc.full_text or "" for doc in inspection.ocr_documents)
    return UploadSuccess(
        inspection_id=inspection.inspection_id,
        status=inspection.processing_status.value,
        filename=inspection.original_filename or "",
        document_type=inspection.document_type or "image",
        pages=inspection.page_count or 0,
        text_length=len(full_text),
        blocks_detected=len(inspection.ocr_blocks),
    )


def _to_out(inspection, session: Session) -> InspectionOut:
    pages = [
        OCRPageOut(
            page_number=doc.page_number,
            width=doc.width,
            height=doc.height,
            full_text=doc.full_text or "",
            processed_path=doc.processed_path,
            warped=bool(doc.warped),
        )
        for doc in sorted(inspection.ocr_documents, key=lambda d: d.page_number)
    ]
    blocks = [
        OCRBlockOut(
            block_id=block.block_id,
            page_number=block.page_number,
            text=block.text,
            confidence=float(block.confidence),
            bbox={
                "x": block.x,
                "y": block.y,
                "width": block.width,
                "height": block.height,
            },
            line_number=block.line_number,
            block_number=block.block_number,
        )
        for block in sorted(inspection.ocr_blocks, key=lambda b: (b.page_number, b.id))
    ]
    return InspectionOut(
        inspection_id=inspection.inspection_id,
        status=inspection.processing_status.value,
        created_at=inspection.created_at,
        file={
            "original_filename": inspection.original_filename or "",
            "document_type": inspection.document_type or "image",
        },
        ocr={
            "pages": pages,
            "blocks": blocks,
            "full_text": "\n\n".join(page.full_text for page in pages),
            "blocks_detected": len(blocks),
            "average_confidence": average_confidence(session, inspection.id),
        },
    )


@router.get("/{inspection_id}")
def get_inspection(inspection_id: str, session: Session = Depends(get_db)) -> InspectionOut:
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    return _to_out(inspection, session)


@router.get("/{inspection_id}/image")
def get_inspection_image(inspection_id: str, session: Session = Depends(get_db)) -> FileResponse:
    """Serve the stored original upload (never exposes server paths)."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    if not inspection.file_path or inspection.processing_status is None:
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "No stored file for this inspection."})
    path = Path(inspection.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "Stored file is missing."})
    media_type = inspection.mime_type or (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=inspection.original_filename or path.name)
