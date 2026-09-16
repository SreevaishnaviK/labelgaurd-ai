"""Shared backend test fixtures.

The CV service is exercised through a real local HTTP stub so the full
orchestration path (multipart -> client -> persistence) runs without
Tesseract installed. The stub returns fixed fixture OCR payloads clearly
used only for testing orchestration — production never fabricates OCR.
"""
import io
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    from PIL import Image

    Image.new("RGB", (80, 40), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _fake_ocr_blocks() -> list[dict]:
    return [
        {
            "id": "block_001",
            "text": "MRP ₹68.00",
            "confidence": 96.4,
            "bbox": {"x": 124, "y": 82, "width": 280, "height": 54},
            "line_number": 1,
            "block_number": 4,
            "page_number": 1,
        }
    ]


def _fake_ocr_payload() -> dict:
    blocks = _fake_ocr_blocks()
    return {
        "status": "success",
        "document_type": "image",
        "pages": [
            {
                "page_number": 1,
                "width": 800,
                "height": 400,
                "full_text": "\n".join(b["text"] for b in blocks),
                "blocks": blocks,
                "processed_image": "processed/stub-doc/page-1.png",
                "warped": False,
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


def _fake_ai_fields() -> list[dict]:
    return [
        {
            "field_name": "mrp",
            "status": "detected",
            "value": {"amount": 68.0, "currency": "INR"},
            "raw_text": "MRP ₹68.00",
            "ocr_confidence": 96.4,
            "extraction_confidence": 95.0,
            "method": "deterministic",
            "evidence": [{"ocr_block_id": "block_001", "page_number": 1}],
        }
    ]


class _StubAIHandler(BaseHTTPRequestHandler):
    behavior = {"mode": "ok", "provider": "none"}
    last_request: dict = {}

    def do_POST(self):
        import json

        length = int(self.headers.get("Content-Length", 0))
        _StubAIHandler.last_request = json.loads(self.rfile.read(length) or b"{}")
        mode = self.behavior["mode"]
        if mode == "unavailable":
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if mode == "error":
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"status": "success", "provider": self.behavior["provider"], "fields": _fake_ai_fields()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Health with provider name (Phase 4) for system-status tests."""
        import json

        body = json.dumps(
            {"status": "ok", "service": "stub-ai", "provider": self.behavior["provider"]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def stub_ai():
    """AI stub: ok mode returns one detected field; modes switch failure paths."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = get_settings()
    original_url, original_timeout = settings.ai_service_url, settings.ai_timeout_seconds
    settings.ai_service_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    settings.ai_service_url = original_url
    settings.ai_timeout_seconds = original_timeout
    server.shutdown()


@pytest.fixture(scope="module")
def real_legal_engine():
    """Run the actual legal-engine service (real rule evaluators) on a free port.

    The legal-engine and backend packages are both named `app`, so an
    in-process import would collide; a subprocess keeps each service's own
    environment. Every rule outcome the tests assert is therefore the REAL
    evaluator's — no legal logic is duplicated or mocked.
    """
    import socket

    import httpx

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [
            str(Path(__file__).resolve().parents[2] / "legal-engine" / ".venv" / "Scripts" / "python.exe"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(Path(__file__).resolve().parents[2] / "legal-engine"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        import time

        time.sleep(0.2)
    settings = get_settings()
    original_url, original_timeout = settings.legal_engine_url, settings.legal_engine_timeout_seconds
    settings.legal_engine_url = base
    yield base
    settings.legal_engine_url = original_url
    settings.legal_engine_timeout_seconds = original_timeout
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """TestClient bound to an isolated SQLite DB + temp upload dir."""
    import os

    import sqlalchemy as sa
    import app.api.inspections as inspections_api
    import app.database as database
    from app.database import Base

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    engine_url = "sqlite:///./.test-inspections.db"
    test_engine = sa.create_engine(engine_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    TestingSession = sa.orm.sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.database.engine", test_engine)
    monkeypatch.setattr(inspections_api, "get_db", database.get_db)
    yield TestClient(app_ref())
    test_engine.dispose()
    os.remove(".test-inspections.db")


def app_ref():
    from app.main import app

    return app


def upload(client, name="label.png", mime="image/png", data=None):
    return client.post(
        "/api/v1/inspections/upload",
        files={"file": (name, data if data is not None else png_bytes(), mime)},
    )
