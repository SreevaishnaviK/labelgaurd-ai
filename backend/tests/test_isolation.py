"""Phase 9C backend tests: evidence-integrity gate, cross-field false
positives, and cross-inspection isolation (§19/§20/§25/§26).

The evidence-validation gate runs inside the real upload flow over the stub
CV/AI services: a field whose evidence references missing blocks, or blocks
whose text cannot support the value, is downgraded to ``ambiguous`` — never
silently kept, never deleted. Cross-inspection isolation is proven by two
sequential uploads through the REAL pipeline with different persisted
values; each inspection must contain only its own.
"""
import pytest

from . import conftest as _conftest
from .conftest import upload


def _fields(*items: dict) -> list[dict]:
    return list(items)


def _mrp(amount: float, block_id: str) -> dict:
    return {
        "field_name": "mrp",
        "status": "detected",
        "value": {"amount": amount, "currency": "INR"},
        "raw_text": f"MRP ₹{amount:.2f}",
        "ocr_confidence": 96.4,
        "extraction_confidence": 95.0,
        "method": "deterministic",
        "evidence": [{"ocr_block_id": block_id, "page_number": 1}],
    }


def _field(field: dict) -> dict:
    return client.get(f"/api/v1/inspections/{_field.inspection_id}").json()  # placeholder


# --------------------------------------------------------------------------
# Evidence-integrity gate (§19/§20)
# --------------------------------------------------------------------------


def test_missing_evidence_ref_is_downgraded(stub_cv, stub_ai, client, monkeypatch):
    """§20: evidence referencing a block that does not exist on THIS
    inspection (the cross-inspection leak signature) → ambiguous."""
    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _fields(_mrp(68.0, "block_999")))
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["field_name"] == "mrp"
    assert field["status"] == "ambiguous"
    assert field["resolution_status"] == "evidence_missing"


def test_value_not_supported_by_evidence_is_downgraded(stub_cv, stub_ai, client, monkeypatch):
    """§20: MRP 45.00 claimed on evidence that only contains 68.00."""
    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _fields(_mrp(45.0, "block_005")))
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["status"] == "ambiguous"
    assert field["resolution_status"] == "evidence_mismatch"


def test_valid_field_survives_the_gate(stub_cv, stub_ai, client, monkeypatch):
    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _fields(_mrp(68.0, "block_005")))
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["status"] == "detected"
    assert field["value"] == {"amount": 68.0, "currency": "INR"}


def test_allergen_value_cannot_pass_the_gate(stub_cv, stub_ai, client, monkeypatch):
    """§26: 'Contains milk...' claimed as the product name fails §20 — its
    evidence text (consumer-care line) cannot support the value."""
    monkeypatch.setattr(
        _conftest,
        "_fake_ai_fields",
        lambda: _fields(
            {
                "field_name": "product_name",
                "status": "detected",
                "value": {"name": "Contains milk. May contain traces"},
                "raw_text": "Contains milk. May contain traces",
                "ocr_confidence": 90.0,
                "extraction_confidence": 90.0,
                "method": "deterministic",
                "evidence": [{"ocr_block_id": "block_007", "page_number": 1}],
            }
        ),
    )
    inspection_id = upload(client).json()["inspection_id"]
    field = client.get(f"/api/v1/inspections/{inspection_id}").json()["extraction"]["fields"][0]
    assert field["status"] == "ambiguous"
    assert field["resolution_status"] == "evidence_mismatch"


# --------------------------------------------------------------------------
# Cross-inspection isolation (§25 mandatory)
# --------------------------------------------------------------------------


def test_cross_inspection_isolation_ab(stub_cv, stub_ai, client, monkeypatch):
    """Two different products uploaded sequentially through the real pipeline.

    Inspection A: MRP ₹68.00 (block_005 evidence)
    Inspection B: Net Qty 1 kg (block_004 evidence)
    A must never carry B's field/value and B must never carry A's — checked
    through the API and directly in the database (§28).
    """
    fields_a = _fields(_mrp(68.0, "block_005"))
    fields_b = _fields(
        {
            "field_name": "net_quantity",
            "status": "detected",
            "value": {"value": 1.0, "unit": "kg"},
            "raw_text": "Net Qty: 1 kg",
            "ocr_confidence": 96.0,
            "extraction_confidence": 95.0,
            "method": "deterministic",
            "evidence": [{"ocr_block_id": "block_004", "page_number": 1}],
        }
    )
    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: fields_a)
    id_a = upload(client).json()["inspection_id"]
    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: fields_b)
    id_b = upload(client).json()["inspection_id"]

    detail_a = client.get(f"/api/v1/inspections/{id_a}").json()["extraction"]["fields"]
    detail_b = client.get(f"/api/v1/inspections/{id_b}").json()["extraction"]["fields"]
    names_a = {f["field_name"] for f in detail_a}
    names_b = {f["field_name"] for f in detail_b}

    assert names_a == {"mrp"} and names_b == {"net_quantity"}
    assert detail_a[0]["value"] == {"amount": 68.0, "currency": "INR"}
    assert detail_b[0]["value"] == {"value": 1.0, "unit": "kg"}

    # §28: persisted rows are inspection-scoped — no cross foreign keys.
    from app.database import SessionLocal
    from app.models.inspection import ExtractedField, Inspection

    session = SessionLocal()
    try:
        for public_id, expected_name, expected_value in (
            (id_a, "mrp", {"amount": 68.0, "currency": "INR"}),
            (id_b, "net_quantity", {"value": 1.0, "unit": "kg"}),
        ):
            inspection = session.query(Inspection).filter_by(inspection_id=public_id).one()
            rows = (
                session.query(ExtractedField)
                .filter_by(inspection_id=inspection.id, field_name=expected_name)
                .all()
            )
            assert len(rows) == 1
            assert rows[0].value_json == expected_value
        assert session.query(ExtractedField).count() == 2
    finally:
        session.close()
