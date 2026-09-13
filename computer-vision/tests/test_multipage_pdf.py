"""Multi-page PDF handling: pages processed independently (§31).

The poppler rasterizer and the OCR engine are stubbed at their declared
abstraction boundaries so this test runs on hosts without either binary;
preprocessing, block parsing, storage, and the API contract are real. A
real-poppler/Tesseract variant lives in test_ocr_integration.py (Docker).
"""
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import get_settings


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Analyze app with 2-page rasterization and word-level OCR stubs."""
    import app.api.analyze as analyze_mod

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))

    def fake_decode_pdf(_data: bytes, dpi: int = 200):
        pages = []
        for page_number, width in ((1, 800), (2, 640)):
            image = Image.new("RGB", (width, 400), "white")
            ImageDraw.Draw(image).text((20, 40), f"PAGE {page_number} TEXT", fill="black")
            pages.append(image)
        return pages

    class StubEngine:
        def extract(self, image):
            from app.ocr.engine import RawOCRResult, RawWord

            return RawOCRResult(
                words=[RawWord("STUB", 90.0, 10, 10, 60, 24, 1, 1)],
                width=image.shape[1],
                height=image.shape[0],
            )

    monkeypatch.setattr(analyze_mod, "decode_pdf", fake_decode_pdf)
    monkeypatch.setattr(analyze_mod, "get_ocr_engine", lambda name: StubEngine())
    from app.main import app

    return TestClient(app)


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 stub content for rasterizer stub"


def test_multipage_pdf_pages_processed_independently(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["document_type"] == "pdf"
    assert [page["page_number"] for page in body["pages"]] == [1, 2]


def test_multipage_pdf_coordinates_independent(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    page1, page2 = response.json()["pages"]
    # MIN_OCR_EDGE upscaling applies per page; aspect ratios differ per page.
    assert (page1["width"], page1["height"]) == (1280, 640)  # 800x400 upscaled
    assert (page2["width"], page2["height"]) == (1024, 640)  # 640x400 upscaled
    assert (page1["width"], page1["height"]) != (page2["width"], page2["height"])
    for page in (page1, page2):
        block = page["blocks"][0]
        assert block["page_number"] == page["page_number"]
        assert block["bbox"]["x"] >= 0 and block["bbox"]["width"] > 0
    assert page1["blocks"][0]["bbox"]["x"] == page2["blocks"][0]["bbox"]["x"]


def test_multipage_pdf_processed_images_persisted(client: TestClient) -> None:
    from pathlib import Path

    response = client.post(
        "/api/v1/analyze",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    pages = response.json()["pages"]
    settings = get_settings()
    for page in pages:
        stored = Path(settings.upload_dir) / page["processed_image"]
        assert stored.is_file(), stored
        with Image.open(stored) as processed:
            assert (processed.width, processed.height) == (page["width"], page["height"])
        assert page["warped"] is False


def test_pdf_page_numbering_preserved_in_blocks(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("doc.pdf", _pdf_bytes(), "application/pdf")},
    )
    blocks = [block for page in response.json()["pages"] for block in page["blocks"]]
    assert [block["page_number"] for block in blocks] == [1, 2]
    assert [block["id"] for block in blocks] == ["block_001", "block_001"]
