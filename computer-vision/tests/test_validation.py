"""Validation-layer tests (no OCR dependency)."""
import io

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.utils.file_utils import validate_upload


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _upload(name: str, data: bytes, mime: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=name,
        headers=Headers({"content-type": mime}),
    )


def test_png_upload_valid() -> None:
    assert validate_upload(_upload("label.png", _png_bytes(), "image/png"), _png_bytes()) == "png"


def test_jpg_extension_jpeg_content() -> None:
    assert validate_upload(_upload("label.jpg", _png_bytes(), "image/png"), _png_bytes()) == "png"


def test_pdf_upload_valid() -> None:
    assert validate_upload(_upload("label.pdf", _pdf_bytes(), "application/pdf"), _pdf_bytes()) == "pdf"


def test_invalid_extension_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_upload(_upload("label.exe", _png_bytes(), "image/png"), _png_bytes())
    assert exc.value.status_code == 415
    assert exc.value.detail["code"] == "UNSUPPORTED_FILE"


def test_extension_pdf_with_image_content_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_upload(_upload("evil.pdf", _png_bytes(), "application/pdf"), _png_bytes())
    assert exc.value.status_code == 415


def test_gif_content_rejected_despite_name() -> None:
    gif = b"GIF89a" + b"\x00" * 20
    with pytest.raises(HTTPException) as exc:
        validate_upload(_upload("label.png", gif, "image/png"), gif)
    assert exc.value.status_code == 415


def test_empty_file_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_upload(_upload("label.png", b"", "image/png"), b"")
    assert exc.value.status_code == 400


def test_bad_mime_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_upload(_upload("label.png", _png_bytes(), "text/html"), _png_bytes())
    assert exc.value.status_code == 415


def test_oversized_file_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(
        type(get_settings()), "max_upload_size_bytes", property(lambda self: 10)
    )
    big = _png_bytes() + b"\x00" * 100
    with pytest.raises(HTTPException) as exc:
        validate_upload(_upload("label.png", big, "image/png"), big)
    assert exc.value.status_code == 413
