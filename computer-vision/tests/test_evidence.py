"""CV evidence-layer tests (Phase 7).

Synthetic images are drawn with PIL/OpenCV — no Tesseract, no network. The
tests pin the contract: pixels never masquerade as physical units, physical
values exist only with a supplied calibration, and insufficient evidence is
reported rather than guessed.
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.config import get_settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _upload_dir(monkeypatch, tmp_path):
    """Point the service's UPLOAD_DIR at this test's tmp directory."""
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))


def _font(size: int):
    for path in [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _png_bytes(width=800, height=600, boundary=True, text=True, blur=False) -> bytes:
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    if boundary:
        draw.rectangle([40, 40, width - 40, height - 40], outline="black", width=6)
    if text:
        draw.text((width // 2, 90), "PREMIUM WHEAT FLOUR", fill="black", font=_font(48), anchor="mm")
        draw.text((width // 2, 200), "Net Qty: 1 kg", fill="black", font=_font(36), anchor="mm")
        draw.text((width // 2, 320), "MRP Rs. 68.00", fill="black", font=_font(36), anchor="mm")
        draw.text((width // 2, 440), "Manufactured by ABC Foods Pvt Ltd", fill="black", font=_font(28), anchor="mm")
    if blur:
        import cv2
        import numpy as np

        arr = cv2.GaussianBlur(np.array(img), (51, 51), 20)
        img = Image.fromarray(arr)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _blocks(width=800, height=600) -> list[dict]:
    return [
        {"id": "block_001", "text": "PREMIUM WHEAT FLOUR", "confidence": 96.0,
         "bbox": {"x": 150, "y": 60, "width": 500, "height": 60}, "line_number": 1, "block_number": 1, "page_number": 1},
        {"id": "block_002", "text": "Net Qty: 1 kg", "confidence": 95.0,
         "bbox": {"x": 320, "y": 180, "width": 160, "height": 40}, "line_number": 2, "block_number": 2, "page_number": 1},
        {"id": "block_003", "text": "MRP Rs. 68.00", "confidence": 94.0,
         "bbox": {"x": 300, "y": 300, "width": 200, "height": 40}, "line_number": 3, "block_number": 3, "page_number": 1},
    ]


def _fields() -> list[dict]:
    return [
        {"field_name": "product_name", "evidence": [{"ocr_block_id": "block_001", "page_number": 1}]},
        {"field_name": "net_quantity", "evidence": [{"ocr_block_id": "block_002", "page_number": 1}]},
        {"field_name": "mrp", "evidence": [{"ocr_block_id": "block_003", "page_number": 1}]},
        {"field_name": "manufacturer", "evidence": [{"ocr_block_id": "block_404", "page_number": 1}]},
    ]


def _analyze(png: bytes, blocks=None, fields=None, calibration=None, tmp_path=None):
    if tmp_path is not None:
        processed_dir = tmp_path / "processed" / "doc1"
        processed_dir.mkdir(parents=True, exist_ok=True)
        (processed_dir / "page1.png").write_bytes(png)
        # TestClient requests resolve UPLOAD_DIR via the patched settings.
    import json

    payload = {
        "inspection_id": "LGA-TEST-00001",
        "pages": [
            {
                "page_number": 1,
                "width": 800,
                "height": 600,
                "processed_path": "processed/doc1/page1.png",
                "blocks": blocks if blocks is not None else _blocks(),
            }
        ],
        "fields": fields if fields is not None else _fields(),
    }
    if calibration is not None:
        payload["calibration"] = calibration
    response = client.post("/api/v1/evidence/analyze", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _by_type(body: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in body["evidence"]:
        grouped.setdefault(item["evidence_type"], []).append(item)
    return grouped


# A/B. package boundary ----------------------------------------------------------


def test_boundary_detected_on_clear_package(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    boundary = grouped["BOUNDARY"][0]
    assert boundary["verification_status"] == "AUTOMATED"
    assert boundary["bbox"]["width"] > 600 and boundary["bbox"]["height"] > 400
    assert boundary["confidence"] >= 0.5


def test_boundary_insufficient_evidence_when_no_package(tmp_path):
    # No rectangle drawn: a blank page yields no confident boundary.
    grouped = _by_type(_analyze(_png_bytes(boundary=False, text=False), tmp_path=tmp_path))
    boundary = grouped["BOUNDARY"][0]
    assert boundary["verification_status"] == "INSUFFICIENT_EVIDENCE"
    assert boundary["bbox"] is None


# D/E/F/G. candidate PDP + calibration -------------------------------------------


def test_pdp_candidate_detected(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    pdp = [i for i in grouped["PDP_AREA"] if i["unit"] == "px2"]
    assert pdp and pdp[0]["bbox"] is not None
    assert "Candidate" in pdp[0]["note"]
    assert pdp[0]["confidence"] > 0.3


def test_pdp_physical_area_absent_without_calibration(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    assert not any(i["unit"] == "cm2" for i in grouped["PDP_AREA"])


def test_calibration_produces_physical_area(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), calibration={"px_per_mm": 10.0, "source": "test scale"}, tmp_path=tmp_path))
    cm2 = [i for i in grouped["PDP_AREA"] if i["unit"] == "cm2"]
    assert cm2, grouped["PDP_AREA"]
    bbox = cm2[0]["bbox"]
    assert cm2[0]["value"] == pytest.approx((bbox["width"] / 10.0) * (bbox["height"] / 10.0), rel=0.01)
    assert "test scale" in cm2[0]["method"]


# C/H. text geometry -------------------------------------------------------------


def test_text_height_is_pixels_not_mm(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    heights = grouped["TEXT_HEIGHT"]
    tallest = max(_blocks(), key=lambda b: b["bbox"]["height"])
    assert any(i["unit"] == "px" and i["value"] == tallest["bbox"]["height"] for i in heights)
    assert not any(i["unit"] == "mm" for i in heights)


def test_calibration_produces_mm_text_height(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), calibration={"px_per_mm": 8.0, "source": "test"}, tmp_path=tmp_path))
    mm = [i for i in grouped["TEXT_HEIGHT"] if i["unit"] == "mm"]
    assert mm and mm[0]["value"] == pytest.approx(60 / 8.0, rel=0.01)
    assert mm[0]["ocr_block_id"] == "block_001"


# I. declaration regions ----------------------------------------------------------


def test_declaration_regions_linked_to_ocr_blocks(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    regions = grouped["DECLARATION_REGION"]
    by_value = {r["value"]: r for r in regions}
    assert by_value["NET_QUANTITY"]["bbox"]["x"] == 320
    assert by_value["NET_QUANTITY"]["ocr_block_ids"] == ["block_002"]
    assert by_value["MRP"]["ocr_block_ids"] == ["block_003"]
    # Unknown evidence block id -> no region is fabricated for it.
    assert not any(r["field_name"] == "manufacturer" for r in regions)


# J/K. contrast + readability -----------------------------------------------------


def test_contrast_and_readability_measurements(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    assert len(grouped["CONTRAST"]) >= 3
    assert all(0 <= i["value"] <= 1 for i in grouped["CONTRAST"])
    assert len(grouped["READABILITY"]) >= 3
    assert all(i["value"] >= 0 for i in grouped["READABILITY"])


def test_blurred_text_measured_not_judged(tmp_path):
    sharp = _by_type(_analyze(_png_bytes(), tmp_path=tmp_path))
    blurred = _by_type(_analyze(_png_bytes(blur=True), tmp_path=tmp_path))
    sharp_var = [i["value"] for i in sharp["READABILITY"]]
    blurred_var = [i["value"] for i in blurred["READABILITY"]]
    assert max(blurred_var) < max(sharp_var)  # measurement detects the blur
    # The service still reports values; no legal status is attached.
    assert all("verification_status" in i for i in blurred["READABILITY"])


# API robustness ------------------------------------------------------------------


def test_missing_processed_image_is_404():
    payload = {
        "inspection_id": "LGA-TEST-00002",
        "pages": [{"page_number": 1, "width": 800, "height": 600, "processed_path": "processed/none/page1.png", "blocks": []}],
        "fields": [],
    }
    response = client.post("/api/v1/evidence/analyze", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROCESSED_IMAGE_MISSING"


def test_no_blocks_yields_insufficient_pdp(tmp_path):
    grouped = _by_type(_analyze(_png_bytes(), blocks=[], tmp_path=tmp_path))
    assert grouped["PDP_AREA"][0]["verification_status"] == "INSUFFICIENT_EVIDENCE"
