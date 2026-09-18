"""Backend Phase 4 tests: provenance persistence, candidate audit trail,
mode passthrough, and honest system status.

The AI service is exercised through the shared stub (conftest.py); its
"rich" payload is clearly fixture data used to test orchestration and
persistence — production never fabricates extraction fields.
"""
from . import conftest as _conftest
from .conftest import _StubAIHandler, upload


def _rich_ai_fields() -> list[dict]:
    """Fixture: one conflicted field with full provenance + candidates."""
    return [
        {
            "field_name": "mrp",
            "status": "ambiguous",
            "value": None,
            "raw_text": None,
            "ocr_confidence": None,
            "extraction_confidence": 88.0,
            "ai_confidence": 91.5,
            "resolution_status": "conflict",
            "method": "ai_assisted",
            "evidence": [{"ocr_block_id": "block_001", "page_number": 1}],
            "candidates": [
                {
                    "value": {"amount": 68.0, "currency": "INR"},
                    "raw_text": "MRP Rs. 68.00",
                    "method": "deterministic",
                    "confidence": 95.0,
                    "evidence": [{"ocr_block_id": "block_001", "page_number": 1}],
                },
                {
                    "value": {"amount": 72.0, "currency": "INR"},
                    "raw_text": "MRP Rs. 72",
                    "method": "ai_assisted",
                    "confidence": 88.0,
                    "evidence": [{"ocr_block_id": "block_001", "page_number": 1}],
                },
            ],
        }
    ]


def test_provenance_in_get_inspection(stub_cv, stub_ai, client, monkeypatch):
    monkeypatch.setattr(_conftest, "_fake_ai_fields", _rich_ai_fields)
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["method"] == "ai_assisted"
    assert field["resolution_status"] == "conflict"
    assert field["ai_confidence"] == 91.5
    assert field["status"] == "ambiguous" and field["value"] is None
    methods = [c["method"] for c in field["candidates"]]
    assert methods == ["deterministic", "ai_assisted"]
    for candidate in field["candidates"]:
        assert candidate["evidence"] == [{"ocr_block_id": "block_001", "page_number": 1}]


def test_provenance_and_candidates_persisted(stub_cv, stub_ai, client, monkeypatch):
    monkeypatch.setattr(_conftest, "_fake_ai_fields", _rich_ai_fields)
    from app.database import SessionLocal
    from app.models.inspection import ExtractionCandidate, ExtractedField, Inspection

    inspection_id = upload(client).json()["inspection_id"]
    with SessionLocal() as session:
        inspection = session.query(Inspection).filter_by(inspection_id=inspection_id).one()
        field = session.query(ExtractedField).filter_by(inspection_id=inspection.id).one()
        assert float(field.ai_confidence) == 91.5
        assert field.resolution_status == "conflict"
        assert field.method == "ai_assisted"
        candidates = session.query(ExtractionCandidate).filter_by(extracted_field_id=field.id).all()
        assert len(candidates) == 2
        assert {c.method for c in candidates} == {"deterministic", "ai_assisted"}
        # Per-reading evidence survives persistence (normalized design).
        for candidate in candidates:
            assert candidate.evidence_json == [{"ocr_block_id": "block_001", "page_number": 1}]


def test_fallback_provenance_persisted(stub_cv, stub_ai, client, monkeypatch):
    """A deterministic_fallback field keeps its provenance end to end."""
    monkeypatch.setattr(
        _conftest,
        "_fake_ai_fields",
        lambda: [
            {
                "field_name": "mrp",
                "status": "detected",
                "value": {"amount": 68.0, "currency": "INR"},
                "method": "deterministic_fallback",
                "resolution_status": "ai_unavailable",
                "evidence": [{"ocr_block_id": "block_005", "page_number": 1}],
            }
        ],
    )
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["method"] == "deterministic_fallback"
    assert field["resolution_status"] == "ai_unavailable"
    assert field["ai_confidence"] is None


def test_extraction_mode_passthrough_default(stub_cv, stub_ai, client):
    inspection_id = upload(client).json()["inspection_id"]
    assert inspection_id
    assert _StubAIHandler.last_request.get("mode") == "auto"


def test_extraction_mode_passthrough_configured(stub_cv, stub_ai, client, monkeypatch):
    monkeypatch.setattr(_conftest.get_settings(), "extraction_mode", "deterministic")
    upload(client)
    assert _StubAIHandler.last_request.get("mode") == "deterministic"


def test_system_status_reports_ai_provider(stub_ai, client, monkeypatch):
    monkeypatch.setattr(_conftest.get_settings(), "ai_service_url", _conftest.get_settings().ai_service_url)
    _StubAIHandler.behavior = {"mode": "ok", "provider": "openai"}
    try:
        body = client.get("/api/v1/system/status").json()
        assert body["ai"] == "ok"
        assert body["ai_provider"] == "openai"
        assert "key" not in str(body).lower()
    finally:
        _StubAIHandler.behavior = {"mode": "ok", "provider": "none"}


def test_system_status_ai_down_is_unknown_provider(stub_cv, client, monkeypatch):
    monkeypatch.setattr(_conftest.get_settings(), "ai_service_url", "http://127.0.0.1:59999")
    body = client.get("/api/v1/system/status").json()
    assert body["ai"] == "unavailable"
    assert body["ai_provider"] == "unknown"


def test_phase3_shape_unchanged_without_provenance(stub_cv, stub_ai, client):
    """A plain deterministic field (Phase 3 payload) keeps its exact shape."""
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["method"] == "deterministic"
    assert field["ai_confidence"] is None and field["resolution_status"] is None
    assert field["candidates"] is None
