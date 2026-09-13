"""POST /api/v1/analyze — real OCR over uploaded label images/PDFs."""
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.config import get_settings
from app.ocr.engine import get_ocr_engine
from app.ocr.parser import join_full_text, parse_blocks
from app.preprocessing.image_loader import decode_image, decode_pdf
from app.preprocessing.preprocess import preprocess_for_ocr
from app.schemas.vision import AnalyzeSuccess, OCRPage
from app.utils.file_utils import validate_upload
from app.utils.processed_store import save_processed_image

router = APIRouter()


def _processed_root(document_id: str) -> Path:
    """Per-document directory under uploads/processed, created fresh."""
    settings = get_settings()
    root = Path(settings.upload_dir) / "processed" / document_id
    if root.exists():
        shutil.rmtree(root)
    return root


def _analyze_page(image, page_number: int, page_root: Path) -> OCRPage:
    """Preprocess + OCR one page image, persisting the processed variant."""
    settings = get_settings()
    gray, width, height, warped = preprocess_for_ocr(image)
    engine = get_ocr_engine(settings.ocr_engine)
    raw = engine.extract(gray)
    blocks = parse_blocks(raw, page_number)
    processed_name = save_processed_image(page_root, page_number, gray)
    return OCRPage(
        page_number=page_number,
        width=width,
        height=height,
        full_text=join_full_text(blocks),
        blocks=blocks,
        # Path relative to the service's UPLOAD_DIR — the backend mounts the
        # same volume and can serve this file back to the frontend.
        processed_image=f"processed/{page_root.name}/{processed_name}",
        warped=warped,
    )


@router.post("/api/v1/analyze", response_model=AnalyzeSuccess)
def analyze(file: UploadFile = File(...)) -> AnalyzeSuccess:
    started = time.perf_counter()
    data = file.file.read()

    content_format = validate_upload(file, data)  # 415/413 on failure

    try:
        if content_format == "pdf":
            images = decode_pdf(data)
            document_type = "pdf"
        else:
            images = [decode_image(data)]
            document_type = "image"
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "UNREADABLE_DOCUMENT", "message": str(exc)},
        ) from exc

    pages: list[OCRPage] = []
    document_id = f"{int(time.time() * 1000):x}-{id(bytes(data)) & 0xffffff:06x}"
    page_root = _processed_root(document_id)
    try:
        for page_number, image in enumerate(images, start=1):
            pages.append(_analyze_page(image, page_number, page_root))
    except Exception as exc:  # engine/runtime failure — surfaced as 500
        shutil.rmtree(page_root, ignore_errors=True)  # no partial artifacts
        raise HTTPException(
            status_code=500,
            detail={"code": "OCR_ENGINE_FAILURE", "message": f"OCR failed: {exc}"},
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return AnalyzeSuccess(
        status="success",
        document_type=document_type,
        pages=pages,
        metadata={"processing_time_ms": elapsed_ms},
    )
