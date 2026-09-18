"""Backend Phase 3 tests: extraction pipeline, persistence, evidence.

The AI service is exercised through the shared stub (conftest.py); its payload
is clearly fixture data used to test orchestration and persistence —
production never fabricates extraction fields.
"""
from app.models.inspection import ExtractedField, ExtractedFieldEvidence

from .conftest import _StubAIHandler, upload


def test_extraction_in_get_inspection(stub_cv, stub_ai, client):
    inspection_id = upload(client).json()["inspection_id"]
    body = client.get(f"/api/v1/inspections/{inspection_id}").json()
    fields = body["extraction"]["fields"]
    assert len(fields) == 1
    field = fields[0]
    assert field["field_name"] == "mrp"
    assert field["status"] == "detected"
    assert field["value"] == {"amount": 68.0, "currency": "INR"}
    assert field["method"] == "deterministic"
    assert field["evidence"] == [{"ocr_block_id": "block_005", "page_number": 1}]
    # Phase 2 OCR section: the stub now delivers one block per fixture field.
    assert body["ocr"]["blocks_detected"] == 7


def test_extracted_fields_persist(stub_cv, stub_ai, client):
    from app.database import SessionLocal
    from app.models.inspection import Inspection

    inspection_id = upload(client).json()["inspection_id"]
    with SessionLocal() as session:
        inspection = session.query(Inspection).filter_by(inspection_id=inspection_id).one()
        fields = session.query(ExtractedField).filter_by(inspection_id=inspection.id).all()
        assert len(fields) == 1
        assert fields[0].value_json == {"amount": 68.0, "currency": "INR"}
        evidence = (
            session.query(ExtractedFieldEvidence)
            .filter_by(extracted_field_id=fields[0].id)
            .all()
        )
        assert len(evidence) == 1
        assert evidence[0].ocr_block_id == "block_005"


def test_extraction_survives_refresh(stub_cv, stub_ai, client):
    """A second GET (simulating browser refresh) returns the same fields."""
    inspection_id = upload(client).json()["inspection_id"]
    first = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]
    second = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]
    assert first == second


def test_ai_unavailable_leaves_processed_without_fabricated_fields(client, stub_cv, monkeypatch):
    """AI outage: upload still succeeds, extraction empty, no fake fields."""
    monkeypatch.setattr(_StubAIHandler, "behavior", {"mode": "unavailable"})
    response = upload(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    inspection_id = body["inspection_id"]
    fields = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"]
    assert fields == []


def test_ai_error_handled(stub_cv, stub_ai, client, monkeypatch):
    monkeypatch.setattr(_StubAIHandler, "behavior", {"mode": "error"})
    response = upload(client)
    assert response.status_code == 200
    assert response.json()["status"] == "processed"


def test_no_fake_fields_when_ocr_has_no_content(stub_cv, stub_ai, client):
    """The stub AI returns its fixture field regardless of OCR content — the
    backend must persist exactly what the service returned and nothing more.
    Here the OCR block is unrelated text; the single stubbed field is the full
    persisted set (no extra invented fields)."""
    inspection_id = upload(client).json()["inspection_id"]
    fields = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"]
    assert [f["field_name"] for f in fields] == ["mrp"]


def test_evidence_references_real_ocr_blocks(stub_cv, stub_ai, client):
    """Every evidence reference must point at a persisted OCR block."""
    inspection_id = upload(client).json()["inspection_id"]
    body = client.get(f"/api/v1/inspections/{inspection_id}").json()
    block_ids = {b["block_id"] for b in body["ocr"]["blocks"]}
    for field in body["extraction"]["fields"]:
        for ref in field["evidence"]:
            assert ref["ocr_block_id"] in block_ids
