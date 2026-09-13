"""Real OCR integration tests.

These run actual Tesseract when it is available (CI Docker image and dev
machines with the binary installed) and skip cleanly otherwise. OCR is never
mocked: when these tests run, they assert on genuine engine output.
"""
import shutil

import pytest

from app.ocr.engine import get_ocr_engine
from app.preprocessing.preprocess import preprocess_for_ocr

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="tesseract binary not installed on this host; run in Docker image",
)


def _label_image():
    """Render a text label. Uses PIL's default font — good enough for OCR."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    try:
        from PIL import ImageFont

        font = ImageFont.load_default(size=48)
    except TypeError:  # Pillow < 10
        font = ImageFont.load_default()
    draw.text((60, 60), "Premium Wheat Flour", fill="black", font=font)
    draw.text((60, 150), "Net Qty: 1 kg", fill="black", font=font)
    return image


def test_ocr_returns_text() -> None:
    gray, width, height = preprocess_for_ocr(_label_image())
    result = get_ocr_engine("tesseract").extract(gray)
    text = " ".join(word.text for word in result.words)
    assert "Flour" in text or "Premium" in text
    assert width > 0 and height > 0


def test_ocr_returns_confidence_and_boxes() -> None:
    gray, _, _ = preprocess_for_ocr(_label_image())
    result = get_ocr_engine("tesseract").extract(gray)
    assert result.words, "expected at least one OCR word"
    for word in result.words:
        assert 0 <= word.confidence <= 100
        assert word.width > 0 and word.height > 0
        assert word.x >= 0 and word.y >= 0


def test_full_analyze_flow() -> None:
    from fastapi.testclient import TestClient
    import io

    from app.main import app

    buffer = io.BytesIO()
    _label_image().save(buffer, format="PNG")
    buffer.seek(0)

    client = TestClient(app)
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("label.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["document_type"] == "image"
    assert len(body["pages"]) == 1
    page = body["pages"][0]
    assert page["blocks"], "expected real OCR blocks"
    assert page["full_text"].strip()
    for block in page["blocks"]:
        assert 0 <= block["confidence"] <= 100
        assert all(k in block["bbox"] for k in ("x", "y", "width", "height"))
    assert body["metadata"]["processing_time_ms"] >= 0
