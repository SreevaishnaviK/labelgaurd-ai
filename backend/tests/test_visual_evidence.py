"""Backend Phase 7 tests: visual evidence persistence and legal integration.

The CV service is exercised through a local HTTP stub (real behavior is
covered by the CV service's own tests); here the focus is the backend
contract: measurements persist, survive reload, never fabricate physical
values, and feed the legal engine without inventing evidence.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from . import conftest as _conftest
from .conftest import upload


def _evidence_payload() -> dict:
    return {
        "inspection_id": "LGA-STUB",
        "evidence": [
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
            {
                "evidence_id": "ev_pdp_px",
                "evidence_type": "PDP_AREA",
                "page_number": 1,
                "bbox": {"x": 100, "y": 50, "width": 500, "height": 90},
                "value": 45000,
                "unit": "px2",
                "confidence": 0.8,
                "method": "text_band_prominence",
                "verification_status": "AUTOMATED",
                "note": "Candidate Principal Display Panel",
            },
            {
                "evidence_id": "ev_height_px",
                "evidence_type": "TEXT_HEIGHT",
                "page_number": 1,
                "bbox": {"x": 100, "y": 50, "width": 500, "height": 60},
                "value": 60,
                "unit": "px",
                "confidence": 0.96,
                "method": "ocr_block_bbox",
                "verification_status": "AUTOMATED",
                "ocr_block_id": "block_001",
                "note": "Estimated text height in pixels",
            },
            {
                "evidence_id": "ev_contrast1",
                "evidence_type": "CONTRAST",
                "page_number": 1,
                "bbox": {"x": 100, "y": 50, "width": 500, "height": 60},
                "value": 0.83,
                "unit": "normalized_luminance_delta",
                "confidence": 0.96,
                "method": "otsu_luminance_split",
                "verification_status": "AUTOMATED",
                "ocr_block_id": "block_001",
            },
            {
                "evidence_id": "ev_region1",
                "evidence_type": "DECLARATION_REGION",
                "page_number": 1,
                "bbox": {"x": 320, "y": 180, "width": 160, "height": 40},
                "value": "NET_QUANTITY",
                "confidence": 0.95,
                "method": "extraction_evidence_join",
                "verification_status": "AUTOMATED",
                "ocr_block_ids": ["block_001"],
                "field_name": "mrp",
            },
        ],
    }


class _StubEvidenceHandler(BaseHTTPRequestHandler):
    """Serves BOTH CV endpoints: the upload-time OCR payload (so the shared
    cv_service_url keeps working for uploads) and the evidence payload."""

    behavior = {"mode": "ok"}

    def do_POST(self):
        import json

        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.behavior["mode"] == "unavailable":
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if "evidence" not in self.path:
            # OCR endpoint — delegate to the shared fixture payload.
            body = json.dumps(_conftest._fake_ocr_payload()).encode()
            self.send_response(200)
        elif self.behavior["mode"] == "missing_image":
            body = json.dumps(
                {"detail": {"code": "PROCESSED_IMAGE_MISSING", "message": "gone"}}
            ).encode()
            self.send_response(404)
        else:
            body = json.dumps(_evidence_payload()).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def stub_evidence_cv():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubEvidenceHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings = _settings()
    original = settings.cv_service_url
    settings.cv_service_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    settings.cv_service_url = original
    server.shutdown()


def _settings():
    from app.config import get_settings

    return get_settings()


def _run_evidence(client, inspection_id):
    response = client.post(f"/api/v1/inspections/{inspection_id}/evidence")
    assert response.status_code == 200, response.text
    return response.json()


# P/Q. persistence + reload --------------------------------------------------------


def test_evidence_persists_and_survives_reload(stub_cv, stub_ai, stub_evidence_cv, client):
    inspection_id = upload(client).json()["inspection_id"]
    items = _run_evidence(client, inspection_id)
    assert {i["evidence_type"] for i in items} == {
        "BOUNDARY", "PDP_AREA", "TEXT_HEIGHT", "CONTRAST", "DECLARATION_REGION",
    }
    # Fresh API call — from the database, not the response object.
    reloaded = client.get(f"/api/v1/inspections/{inspection_id}").json()["visual_evidence"]
    assert len(reloaded) == len(items)
    assert {i["evidence_id"] for i in reloaded} == {i["evidence_id"] for i in items}


def test_evidence_values_keep_their_units(stub_cv, stub_ai, stub_evidence_cv, client):
    inspection_id = upload(client).json()["inspection_id"]
    _run_evidence(client, inspection_id)
    reloaded = client.get(f"/api/v1/inspections/{inspection_id}").json()["visual_evidence"]
    by_type = {i["evidence_type"]: i for i in reloaded}
    # Pixels stay pixels.
    assert by_type["TEXT_HEIGHT"]["unit"] == "px"
    assert by_type["TEXT_HEIGHT"]["note"] and "pixel" in by_type["TEXT_HEIGHT"]["note"]
    assert by_type["PDP_AREA"]["unit"] == "px2"
    # No physical unit is ever fabricated by the backend.
    assert not any(i["unit"] in ("mm", "cm2") for i in reloaded)


# R. CV failure degradation --------------------------------------------------------


def test_cv_evidence_failure_leaves_inspection_intact(stub_cv, stub_ai, stub_evidence_cv, client):
    inspection_id = upload(client).json()["inspection_id"]
    _StubEvidenceHandler.behavior["mode"] = "unavailable"
    try:
        response = client.post(f"/api/v1/inspections/{inspection_id}/evidence")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "CV_SERVICE_UNAVAILABLE"
        # The inspection still exists with OCR + extraction untouched.
        body = client.get(f"/api/v1/inspections/{inspection_id}").json()
        assert body["ocr"]["blocks_detected"] > 0
        assert body["visual_evidence"] == []
    finally:
        _StubEvidenceHandler.behavior["mode"] = "ok"


# M/N/O. legal-engine integration --------------------------------------------------


def test_evaluation_consumes_visual_evidence(stub_cv, stub_ai, stub_evidence_cv, real_legal_engine, client, monkeypatch):
    monkeypatch.setattr(
        _conftest,
        "_fake_ai_fields",
        lambda: [
            {
                "field_name": "mrp", "status": "detected",
                "value": {"amount": 68.0, "currency": "INR"}, "raw_text": "MRP ₹68.00",
                "ocr_confidence": 96.4, "extraction_confidence": 98.0, "method": "deterministic",
                "evidence": [{"ocr_block_id": "block_001", "page_number": 1}],
            }
        ],
    )
    inspection_id = upload(client).json()["inspection_id"]
    _run_evidence(client, inspection_id)
    evaluation = client.post(f"/api/v1/inspections/{inspection_id}/evaluate").json()
    by_id = {r["rule_id"]: r for r in evaluation["results"]}
    # Rule 9-A received the measured contrast: finding reflects a measurement.
    assert by_id["LMPC-R9-A"]["status"] == "REVIEW_REQUIRED"
    assert by_id["LMPC-R9-A"]["actual_information"]["measured_contrast_ratio"] == 0.83
    # The contrast measurement's block is cited as persisted evidence.
    refs = [(e["evidence_type"], e["ocr_block_id"]) for e in by_id["LMPC-R9-A"]["evidence"]]
    assert ("ocr_block", "block_001") in refs, refs


def test_no_evaluation_input_invents_physical_values(stub_cv, stub_ai, stub_evidence_cv, real_legal_engine, client):
    inspection_id = upload(client).json()["inspection_id"]
    _run_evidence(client, inspection_id)
    evaluation = client.post(f"/api/v1/inspections/{inspection_id}/evaluate").json()
    by_id = {r["rule_id"]: r for r in evaluation["results"]}
    # Without calibration, PDP area in cm2 does not exist — R7-B stays
    # NOT_VERIFIABLE (no letter-height measurement either).
    assert by_id["LMPC-R7-B"]["status"] == "NOT_VERIFIABLE"
    # Rule 11-B MPE: this extraction has no net quantity at all, so no
    # comparison is possible (NOT_VERIFIABLE); and measured_quantity can
    # never be invented from an image in any case.
    assert by_id["LMPC-R11-B"]["status"] == "NOT_VERIFIABLE"
    assert "measured_quantity" not in str(by_id["LMPC-R11-B"]["actual_information"])
