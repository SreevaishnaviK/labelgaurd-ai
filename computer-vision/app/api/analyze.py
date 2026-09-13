"""POST /api/v1/analyze — real OCR over uploaded label images/PDFs."""
import time

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.config import get_settings
from app.ocr.engine import get_ocr_engine
from app.ocr.parser import join_full_text, parse_blocks
from app.preprocessing.image_loader import decode_image, decode_pdf
from app.preprocessing.preprocess import preprocess_for_ocr
from app.schemas.vision import AnalyzeSuccess, OCRPage
from app.utils.file_utils import validate_upload

router = APIRouter()


def _analyze_page(image, page_number: int) -> tuple[OCRPage, str]:
    """Preprocess + OCR one page image. Returns (page_model, engine_name)."""
    settings = get_settings()
    gray, width, height = preprocess_for_ocr(image)
    engine = get_ocr_engine(settings.ocr_engine)
    raw = engine.extract(gray)
    blocks = parse_blocks(raw, page_number)
    return (
        OCRPage(
            page_number=page_number,
            width=width,
            height=height,
            full_text=join_full_text(blocks),
            blocks=blocks,
        ),
        settings.ocr_engine,
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
    try:
        for page_number, image in enumerate(images, start=1):
            page, _engine_name = _analyze_page(image, page_number)
            pages.append(page)
    except Exception as exc:  # engine/runtime failure — surfaced as 500
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
