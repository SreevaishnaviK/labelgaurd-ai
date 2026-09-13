"""Backend Phase 2 tests.

The CV service is exercised through the shared stub fixtures in conftest.py
so the full orchestration path (multipart -> client -> persistence) runs
without Tesseract installed. Stub OCR payloads are fixture data used only for
testing orchestration — production never fabricates OCR.
"""
import pytest

from app.config import get_settings
from app.models.inspection import Inspection, OCRBlock, OCRDocument

from .conftest import png_bytes, upload


def test_upload_valid_image(stub_cv, stub_ai, client):
    response = upload(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["inspection_id"].startswith("LGA-2026-")
    assert body["document_type"] == "image"
    assert body["pages"] == 1
    assert body["blocks_detected"] == 1
    assert body["text_length"] > 0


def test_upload_invalid_file(stub_cv, stub_ai, client):
    response = upload(client, name="virus.exe", mime="application/octet-stream", data=b"MZ...")
    assert response.status_code == 415


def test_upload_pdf(stub_cv, stub_ai, client):
    response = upload(client, name="label.pdf", mime="application/pdf", data=b"%PDF-1.4\nminimal")
    assert response.status_code == 200
    assert response.json()["document_type"] == "pdf"


def test_sequential_inspection_ids(stub_cv, stub_ai, client):
    first = upload(client).json()["inspection_id"]
    second = upload(client).json()["inspection_id"]
    assert int(first.split("-")[-1]) + 1 == int(second.split("-")[-1])


def test_get_inspection(stub_cv, stub_ai, client):
    inspection_id = upload(client).json()["inspection_id"]
    response = client.get(f"/api/v1/inspections/{inspection_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["inspection_id"] == inspection_id
    assert body["file"]["original_filename"] == "label.png"
    assert body["ocr"]["blocks_detected"] == 1
    assert body["ocr"]["blocks"][0]["bbox"] == {"x": 124, "y": 82, "width": 280, "height": 54}


def test_get_missing_inspection(client):
    assert client.get("/api/v1/inspections/LGA-2026-99999").status_code == 404


def test_database_persistence(stub_cv, stub_ai, client):
    import sqlalchemy as sa

    from app.database import SessionLocal

    inspection_id = upload(client).json()["inspection_id"]
    with SessionLocal() as session:
        inspection = session.query(Inspection).filter_by(inspection_id=inspection_id).one()
        assert inspection.original_filename == "label.png"
        assert inspection.page_count == 1
        assert session.query(OCRDocument).filter_by(inspection_id=inspection.id).count() == 1
        assert session.query(OCRBlock).filter_by(inspection_id=inspection.id).count() == 1


def test_original_file_preserved(stub_cv, stub_ai, client):
    from pathlib import Path

    body = upload(client).json()
    client.get(f"/api/v1/inspections/{body['inspection_id']}")
    uploads_root = Path(get_settings().upload_dir).resolve()
    stored = list(uploads_root.rglob("*.png"))
    assert stored, "original upload must be preserved on disk"


def test_cv_service_unavailable(client, monkeypatch, stub_ai):
    monkeypatch.setattr(get_settings(), "cv_service_url", "http://127.0.0.1:59999")
    response = upload(client)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CV_SERVICE_UNAVAILABLE"


def test_cv_service_timeout(client, stub_cv, monkeypatch, stub_ai):
    from .conftest import _StubCVHandler

    _StubCVHandler.behavior["mode"] = "timeout"
    monkeypatch.setattr(get_settings(), "cv_timeout_seconds", 1)
    try:
        response = upload(client)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "CV_SERVICE_UNAVAILABLE"
    finally:
        _StubCVHandler.behavior["mode"] = "ok"


def test_cv_rejection_forwarded(client, stub_cv, stub_ai):
    from .conftest import _StubCVHandler

    _StubCVHandler.behavior["mode"] = "reject"
    try:
        response = upload(client)
        assert response.status_code == 503
    finally:
        _StubCVHandler.behavior["mode"] = "ok"


def test_inspection_image_endpoint(stub_cv, stub_ai, client):
    inspection_id = upload(client).json()["inspection_id"]
    response = client.get(f"/api/v1/inspections/{inspection_id}/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
