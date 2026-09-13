"""Backend Phase 2 tests.

The CV service is exercised through a real local HTTP stub so the full
orchestration path (multipart -> client -> persistence) runs without
Tesseract installed. The stub returns fixed fixture OCR payloads clearly
used only for testing orchestration — production never fabricates OCR.
"""
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import app
from app.models.inspection import Inspection, OCRBlock, OCRDocument


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (80, 40), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _fake_ocr_payload() -> dict:
    return {
        "status": "success",
        "document_type": "image",
        "pages": [
            {
                "page_number": 1,
                "width": 800,
                "height": 400,
                "full_text": "MRP ₹68.00",
                "blocks": [
                    {
                        "id": "block_001",
                        "text": "MRP ₹68.00",
                        "confidence": 96.4,
                        "bbox": {"x": 124, "y": 82, "width": 280, "height": 54},
                        "line_number": 1,
                        "block_number": 4,
                        "page_number": 1,
                    }
                ],
            }
        ],
        "metadata": {"processing_time_ms": 5},
    }


class _StubCVHandler(BaseHTTPRequestHandler):
    behavior = {"mode": "ok"}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        mode = self.behavior["mode"]
        if mode == "timeout":
            import time

            time.sleep(2)
            body = b"{}"
            status = 200
        elif mode == "reject":
            body = b'{"detail": {"code": "UNSUPPORTED_FILE", "message": "bad file"}}'
            status = 415
        elif mode == "error":
            body = b"boom"
            status = 500
        else:
            import json

            body = json.dumps(_fake_ocr_payload()).encode()
            status = 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def stub_cv():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubCVHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = get_settings()
    original_url, original_timeout = settings.cv_service_url, settings.cv_timeout_seconds
    settings.cv_service_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    settings.cv_service_url = original_url
    settings.cv_timeout_seconds = original_timeout
    server.shutdown()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """TestClient bound to an isolated SQLite DB + temp upload dir."""
    import sqlalchemy as sa
    from app.database import Base, SessionLocal, engine

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    engine_url = "sqlite:///./.test-inspections.db"
    test_engine = sa.create_engine(engine_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    TestingSession = sa.orm.sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.database.engine", test_engine)
    import app.database as database
    import app.api.inspections as inspections_api

    monkeypatch.setattr(inspections_api, "get_db", database.get_db)
    yield TestClient(app)
    test_engine.dispose()
    import os

    os.remove(".test-inspections.db")


def _upload(client, name="label.png", mime="image/png", data=None):
    return client.post(
        "/api/v1/inspections/upload",
        files={"file": (name, data if data is not None else _png_bytes(), mime)},
    )


def test_upload_valid_image(stub_cv, client):
    response = _upload(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["inspection_id"].startswith("LGA-2026-")
    assert body["document_type"] == "image"
    assert body["pages"] == 1
    assert body["blocks_detected"] == 1
    assert body["text_length"] > 0


def test_upload_invalid_file(stub_cv, client):
    response = _upload(client, name="virus.exe", mime="application/octet-stream", data=b"MZ...")
    assert response.status_code == 415


def test_upload_pdf(stub_cv, client):
    response = _upload(client, name="label.pdf", mime="application/pdf", data=b"%PDF-1.4\nminimal")
    assert response.status_code == 200
    assert response.json()["document_type"] == "pdf"


def test_sequential_inspection_ids(stub_cv, client):
    first = _upload(client).json()["inspection_id"]
    second = _upload(client).json()["inspection_id"]
    assert int(first.split("-")[-1]) + 1 == int(second.split("-")[-1])


def test_get_inspection(stub_cv, client):
    inspection_id = _upload(client).json()["inspection_id"]
    response = client.get(f"/api/v1/inspections/{inspection_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["inspection_id"] == inspection_id
    assert body["file"]["original_filename"] == "label.png"
    assert body["ocr"]["blocks_detected"] == 1
    assert body["ocr"]["blocks"][0]["bbox"] == {"x": 124, "y": 82, "width": 280, "height": 54}


def test_get_missing_inspection(client):
    assert client.get("/api/v1/inspections/LGA-2026-99999").status_code == 404


def test_database_persistence(stub_cv, client):
    import sqlalchemy as sa

    from app.database import SessionLocal

    inspection_id = _upload(client).json()["inspection_id"]
    with SessionLocal() as session:
        inspection = session.query(Inspection).filter_by(inspection_id=inspection_id).one()
        assert inspection.original_filename == "label.png"
        assert inspection.page_count == 1
        assert session.query(OCRDocument).filter_by(inspection_id=inspection.id).count() == 1
        assert session.query(OCRBlock).filter_by(inspection_id=inspection.id).count() == 1


def test_original_file_preserved(stub_cv, client, tmp_path):
    from pathlib import Path

    body = _upload(client).json()
    inspection = client.get(f"/api/v1/inspections/{body['inspection_id']}").json()
    uploads_root = Path(get_settings().upload_dir).resolve()
    stored = list(uploads_root.rglob("*.png"))
    assert stored, "original upload must be preserved on disk"


def test_cv_service_unavailable(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "cv_service_url", "http://127.0.0.1:59999")
    response = _upload(client)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CV_SERVICE_UNAVAILABLE"


def test_cv_service_timeout(client, stub_cv, monkeypatch, tmp_path):
    _StubCVHandler.behavior["mode"] = "timeout"
    monkeypatch.setattr(get_settings(), "cv_timeout_seconds", 1)
    try:
        response = _upload(client)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "CV_SERVICE_UNAVAILABLE"
    finally:
        _StubCVHandler.behavior["mode"] = "ok"


def test_cv_rejection_forwarded(client, stub_cv):
    _StubCVHandler.behavior["mode"] = "reject"
    try:
        response = _upload(client)
        assert response.status_code == 503
    finally:
        _StubCVHandler.behavior["mode"] = "ok"


def test_inspection_image_endpoint(stub_cv, client):
    inspection_id = _upload(client).json()["inspection_id"]
    response = client.get(f"/api/v1/inspections/{inspection_id}/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
