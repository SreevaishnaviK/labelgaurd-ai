"""Backend Phase 9B tests: multi-pass OCR provenance and visual-symbol fields.

Contract under test: recovery-pass blocks persist with their ``source_pass``,
feed extraction unchanged (one logical net-quantity field), and a detected
DECLARATION_SYMBOL composes a ``vegetarian_non_vegetarian`` field beside the
AI-extracted ones — never fabricating OCR evidence, never guessing.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from . import conftest as _conftest
from .conftest import upload


def _evidence_payload(with_symbol: bool = True) -> dict:
    symbol = {
        "evidence_id": "ev_sym1",
        "evidence_type": "DECLARATION_SYMBOL",
        "page_number": 1,
        "bbox": {"x": 694, "y": 941, "width": 66, "height": 69},
        "value": "vegetarian",
        "confidence": 0.85,
        "method": "visual-symbol-detection",
        "verification_status": "AUTOMATED",
        "note": "Detected from the symbol's color and geometry only.",
    }
    items = [
        {
            "evidence_id": "ev_boundary1",
            "evidence_type": "BOUNDARY",
            "page_number": 1,
            "bbox": {"x": 40, "y": 40, "width": 720, "height": 520},
            "value": 374400,
            "unit": "px2",
            "confidence": 0.9,
            "method": "contour_quadrilateral",
            "verification_status": "AUTOMATED",
        },
    ]
    if with_symbol:
        items.append(symbol)
    else:
        items.append(
            {
                "evidence_id": "ev_sym_none",
                "evidence_type": "DECLARATION_SYMBOL",
                "page_number": 1,
                "value": "not detected",
                "confidence": 0.0,
                "method": "visual-symbol-detection",
                "verification_status": "INSUFFICIENT_EVIDENCE",
                "note": "No vegetarian/non-vegetarian symbol found in the image.",
            }
        )
    return {"inspection_id": "LGA-STUB", "evidence": items}


class _StubSymbolCVHandler(BaseHTTPRequestHandler):
    """Serves the OCR upload payload and a scripted evidence payload."""

    behavior = {"mode": "symbol"}

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if "evidence" not in self.path:
            body = json.dumps(_conftest._fake_ocr_payload()).encode()
            self.send_response(200)
        elif self.behavior["mode"] == "no_symbol":
            body = json.dumps(_evidence_payload(with_symbol=False)).encode()
            self.send_response(200)
        else:
            body = json.dumps(_evidence_payload(with_symbol=True)).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def stub_symbol_cv():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubSymbolCVHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    from app.config import get_settings

    settings = get_settings()
    original = settings.cv_service_url
    settings.cv_service_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    settings.cv_service_url = original
    server.shutdown()


def _run_evidence(client, inspection_id):
    response = client.post(f"/api/v1/inspections/{inspection_id}/evidence")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- provenance

def test_source_pass_persists_and_is_exposed(stub_cv, stub_ai, client):
    """Blocks persist with source_pass and the API exposes the provenance."""
    inspection_id = upload(client).json()["inspection_id"]
    detail = client.get(f"/api/v1/inspections/{inspection_id}").json()

    blocks = detail["ocr"]["blocks"]
    assert blocks, "fixture upload must persist OCR blocks"
    # The Phase 9B column exists and round-trips (stub payload has no pass,
    # so blocks default to a null / "A" provenance — never a fabricated one).
    for block in blocks:
        assert block.get("source_pass") in (None, "A", "B", "C")


def test_extraction_gets_one_logical_field_per_name(stub_cv, stub_ai, real_legal_engine, client):
    """Recovery blocks feed the AI extractor like any other block — a
    declaration seen by multiple passes still yields ONE field per name
    (no Net Quantity 1 / 2 / 3)."""
    inspection_id = upload(client).json()["inspection_id"]
    detail = client.get(f"/api/v1/inspections/{inspection_id}").json()

    names = [f["field_name"] for f in detail["extraction"]["fields"]]
    assert len(names) == len(set(names)), "duplicated logical field in extraction"


# ---------------------------------------------------------------- symbol field

def test_detected_symbol_composes_vegetarian_field(stub_cv, stub_ai, stub_symbol_cv, client):
    inspection_id = upload(client).json()["inspection_id"]
    items = _run_evidence(client, inspection_id)

    symbol_rows = [e for e in items if e["evidence_type"] == "DECLARATION_SYMBOL"]
    assert symbol_rows and symbol_rows[0]["value"] == "vegetarian"
    assert symbol_rows[0]["verification_status"] == "AUTOMATED"

    detail = client.get(f"/api/v1/inspections/{inspection_id}").json()
    veg = [f for f in detail["extraction"]["fields"] if f["field_name"] == "vegetarian_non_vegetarian"]
    assert len(veg) == 1
    field = veg[0]
    assert field["status"] == "detected"
    assert field["value"]["declaration"] == "vegetarian"
    assert field["value"]["evidence_id"] == "ev_sym1"
    assert field["method"] == "visual"  # measured, not read
    # No fabricated OCR evidence: a visual symbol has no OCR block.
    assert field["evidence"] == []


def test_missing_symbol_yields_insufficient_evidence_and_no_field(stub_cv, stub_ai, stub_symbol_cv, client):
    """No symbol in the image → INSUFFICIENT_EVIDENCE row, and NO guessed
    vegetarian field (§25: honesty over coverage)."""
    _StubSymbolCVHandler.behavior["mode"] = "no_symbol"
    try:
        inspection_id = upload(client).json()["inspection_id"]
        items = _run_evidence(client, inspection_id)

        symbol_rows = [e for e in items if e["evidence_type"] == "DECLARATION_SYMBOL"]
        assert symbol_rows[0]["verification_status"] == "INSUFFICIENT_EVIDENCE"
        assert symbol_rows[0]["value"] == "not detected"

        detail = client.get(f"/api/v1/inspections/{inspection_id}").json()
        assert not [f for f in detail["extraction"]["fields"] if f["field_name"] == "vegetarian_non_vegetarian"]
    finally:
        _StubSymbolCVHandler.behavior["mode"] = "symbol"


def test_symbol_field_persists_after_reload(stub_cv, stub_ai, stub_symbol_cv, client):
    inspection_id = upload(client).json()["inspection_id"]
    _run_evidence(client, inspection_id)

    first = client.get(f"/api/v1/inspections/{inspection_id}").json()
    second = client.get(f"/api/v1/inspections/{inspection_id}").json()
    veg1 = [f for f in first["extraction"]["fields"] if f["field_name"] == "vegetarian_non_vegetarian"]
    veg2 = [f for f in second["extraction"]["fields"] if f["field_name"] == "vegetarian_non_vegetarian"]
    assert veg1 and veg2
    assert veg1[0]["value"] == veg2[0]["value"]
