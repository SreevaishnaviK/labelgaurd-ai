"""File validation and safety utilities.

Validation layers (never trust the filename alone):
1. Extension allow-list
2. Declared MIME type allow-list
3. Magic-byte sniffing of the actual content
4. Size limit
"""
from fastapi import HTTPException, UploadFile

from app.config import get_settings

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}

# Magic-byte signatures for real content sniffing
_MAGIC = {
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
    "pdf": b"%PDF-",
}

SUPPORTED_MESSAGE = "Only PNG, JPG, JPEG and PDF files are supported."


def _fail(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _sniff_format(data: bytes) -> str | None:
    """Detect the true file format from magic bytes."""
    for fmt, signature in _MAGIC.items():
        if data.startswith(signature):
            return "jpeg" if fmt == "jpg" else fmt
    return None


def validate_upload(file: UploadFile, data: bytes) -> str:
    """Validate an upload and return its canonical format ('png'|'jpeg'|'pdf').

    Raises HTTPException with structured error details on any failure.
    """
    settings = get_settings()

    # 1. Size
    if len(data) == 0:
        raise _fail(400, "EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > settings.max_upload_size_bytes:
        raise _fail(
            413,
            "FILE_TOO_LARGE",
            f"File exceeds the {settings.max_upload_size_mb} MB limit.",
        )

    # 2. Extension (from filename, case-insensitive)
    filename = file.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)

    # 3. Declared MIME type
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_MIME_TYPES:
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)

    # 4. Actual content (never trust name/MIME alone)
    sniffed = _sniff_format(data)
    if sniffed is None:
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)
    # A jpeg content sniff of a .png file is accepted as jpeg either way;
    # what matters is the content is a genuinely supported image/document.
    if extension == "pdf" and sniffed != "pdf":
        raise _fail(415, "UNSUPPORTED_FILE", SUPPORTED_MESSAGE)

    return sniffed
