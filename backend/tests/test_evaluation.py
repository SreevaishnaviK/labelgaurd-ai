"""Backend Phase 6 tests: the end-to-end compliance evaluation pipeline.

The legal engine is exercised as the REAL service (spawned from its own
venv by the `real_legal_engine` fixture) — no legal logic is duplicated or
mocked. Extraction comes from the AI stub's fixture fields; outcomes below
are pinned to the real evaluator's behavior.
"""
import httpx
import pytest

from . import conftest as _conftest
from .conftest import upload

# Scenario A fixture: a realistic detected-field set (values mirror what the
# deterministic extractor emits for a complete label).
_FULL_FIELDS = [
    {
        "field_name": "product_name", "status": "detected",
        "value": {"name": "Premium Wheat Flour"}, "raw_text": "PREMIUM WHEAT FLOUR",
        "ocr_confidence": 96.0, "extraction_confidence": 97.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_001", "page_number": 1}],
    },
    {
        "field_name": "manufacturer", "status": "detected",
        "value": {"name": "ABC Foods Pvt Ltd"}, "raw_text": "Manufactured by ABC Foods Pvt Ltd",
        "ocr_confidence": 95.0, "extraction_confidence": 96.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_002", "page_number": 1}],
    },
    {
        "field_name": "manufacturer_address", "status": "detected",
        "value": {"address": "Plot 12, Industrial Estate, Vijayawada, Andhra Pradesh"},
        "raw_text": "Plot 12, Industrial Estate, Vijayawada, Andhra Pradesh",
        "ocr_confidence": 94.0, "extraction_confidence": 95.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_003", "page_number": 1}],
    },
    {
        "field_name": "net_quantity", "status": "detected",
        "value": {"value": 1, "unit": "kg"}, "raw_text": "Net Qty: 1 kg",
        "ocr_confidence": 96.4, "extraction_confidence": 98.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_004", "page_number": 1}],
    },
    {
        "field_name": "mrp", "status": "detected",
        "value": {"amount": 68.0, "currency": "INR"}, "raw_text": "MRP ₹68.00",
        "ocr_confidence": 96.4, "extraction_confidence": 98.2, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_005", "page_number": 1}],
    },
    {
        "field_name": "manufacturing_date", "status": "detected",
        "value": {"date": "08/2026"}, "raw_text": "MFG 08/2026",
        "ocr_confidence": 95.5, "extraction_confidence": 97.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_006", "page_number": 1}],
    },
    {
        "field_name": "consumer_care", "status": "detected",
        "value": {"contact": "care@abcfoods.example"}, "raw_text": "Consumer Care: care@abcfoods.example",
        "ocr_confidence": 94.0, "extraction_confidence": 95.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_007", "page_number": 1}],
    },
]

_MINIMAL_FIELDS = [_FULL_FIELDS[4]]  # MRP only


def _use_fields(monkeypatch, fields):
    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: fields)


def _evaluate(client, inspection_id):
    response = client.post(f"/api/v1/inspections/{inspection_id}/evaluate")
    assert response.status_code == 200, response.text
    return response.json()


def _by_id(evaluation):
    return {r["rule_id"]: r for r in evaluation["results"]}


# A. complete package ------------------------------------------------------------


def test_complete_package_evaluates_all_rules(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _FULL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    evaluation = _evaluate(client, inspection_id)
    by_id = _by_id(evaluation)
    # The real registry ran: 18 rules (17 structural + R11-B MPE).
    assert len(evaluation["results"]) == 18
    assert by_id["LMPC-R6-A"]["status"] == "COMPLIANT"
    assert by_id["LMPC-R6-C"]["status"] == "COMPLIANT"
    assert by_id["LMPC-R6-E"]["status"] == "COMPLIANT"
    assert by_id["LMPC-R6-F"]["status"] == "COMPLIANT"
    assert by_id["LMPC-R10-A"]["status"] == "COMPLIANT"
    assert by_id["LMPC-R10-C"]["status"] == "COMPLIANT"
    # Unmeasured physical checks stay REVIEW/NOT_VERIFIABLE — never violations.
    assert by_id["LMPC-R11-B"]["status"] == "REVIEW_REQUIRED"
    assert by_id["LMPC-R7-B"]["status"] == "NOT_VERIFIABLE"
    # Overall status is derived backend-side from real rule states.
    assert evaluation["overall_status"] == "REVIEW_REQUIRED"
    assert evaluation["engine_version"]


def test_evidence_references_point_to_real_data(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _FULL_FIELDS)
    # Fixture extraction cites block_001..block_007; give the CV stub the same
    # blocks so evidence integrity is exercised against consistent data.
    def _fixture_blocks():
        from .conftest import _fake_ocr_blocks

        return [
            {
                "id": f"block_{i:03d}",
                "text": field["raw_text"],
                "confidence": field["ocr_confidence"],
                "bbox": {"x": 10 * i, "y": 80 + 10 * i, "width": 280, "height": 40},
                "line_number": i,
                "block_number": i,
                "page_number": 1,
            }
            for i, field in enumerate(_FULL_FIELDS, start=1)
        ]

    monkeypatch.setattr(_conftest, "_fake_ocr_blocks", _fixture_blocks)
    inspection_id = upload(client).json()["inspection_id"]
    inspection = client.get(f"/api/v1/inspections/{inspection_id}").json()
    evaluation = _evaluate(client, inspection_id)
    real_block_ids = {b["block_id"] for b in inspection["ocr"]["blocks"]}
    for result in evaluation["results"]:
        for ref in result["evidence"]:
            if ref["evidence_type"] == "ocr_block":
                assert ref["ocr_block_id"] in real_block_ids
            if ref["evidence_type"] == "extracted_field":
                names = {f["field_name"] for f in inspection["extraction"]["fields"]}
                assert ref["evidence_reference"] in names
    # The MRP rule carries traceable evidence back to its OCR block.
    mrp = _by_id(evaluation)["LMPC-R6-E"]
    types = {ref["evidence_type"] for ref in mrp["evidence"]}
    assert "extracted_field" in types and "ocr_block" in types
    assert any(ref["ocr_block_id"] == "block_005" for ref in mrp["evidence"])


# B/D. missing vs present declarations ------------------------------------------


def test_missing_manufacturer_is_never_a_violation(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _MINIMAL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    by_id = _by_id(_evaluate(client, inspection_id))
    # The builder never sets label_fully_processed, so absence is NOT provable.
    assert by_id["LMPC-R6-A"]["status"] == "NOT_VERIFIABLE"
    assert by_id["LMPC-R10-A"]["status"] == "NOT_VERIFIABLE"
    assert by_id["LMPC-R6-A"]["requires_officer_verification"] is True


def test_valid_mrp_is_compliant(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _MINIMAL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    assert _by_id(_evaluate(client, inspection_id))["LMPC-R6-E"]["status"] == "COMPLIANT"


def test_ambiguous_field_never_feeds_the_engine(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _FULL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    _evaluate(client, inspection_id)
    by_id = _by_id(_evaluate(client, inspection_id))
    assert by_id["LMPC-R6-A"]["status"] == "COMPLIANT"  # baseline sanity
    monkeypatch.setattr(
        _conftest,
        "_fake_ai_fields",
        lambda: [{**_FULL_FIELDS[4], "status": "ambiguous", "value": None}],
    )
    inspection_id = upload(client).json()["inspection_id"]
    by_id = _by_id(_evaluate(client, inspection_id))
    # Ambiguous MRP is not silently converted into a value — or a violation.
    assert by_id["LMPC-R6-E"]["status"] == "NOT_VERIFIABLE"


# E/F. measurements --------------------------------------------------------------


def test_pdp_measurement_is_required_before_height_check(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _MINIMAL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    by_id = _by_id(_evaluate(client, inspection_id))
    assert by_id["LMPC-R7-A"]["status"] == "NOT_VERIFIABLE"
    assert by_id["LMPC-R7-B"]["status"] == "NOT_VERIFIABLE"
    # No fabricated visual evidence anywhere in the builder payload.
    assert by_id["LMPC-R7-A"]["actual_information"] == {}


# G/H/I/J/K. engine behaviors through the pipeline -------------------------------


def test_engine_unavailable_returns_503(stub_cv, stub_ai, client, monkeypatch):
    settings = _settings()
    monkeypatch.setattr(settings, "legal_engine_url", "http://127.0.0.1:9")
    _use_fields(monkeypatch, _MINIMAL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    response = client.post(f"/api/v1/inspections/{inspection_id}/evaluate")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LEGAL_ENGINE_UNAVAILABLE"


def test_no_extraction_returns_409(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    settings = _settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    inspection_id = upload(client).json()["inspection_id"]
    response = client.post(f"/api/v1/inspections/{inspection_id}/evaluate")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EXTRACTION_NOT_AVAILABLE"


def test_unknown_inspection_404(stub_cv, stub_ai, client):
    assert client.post("/api/v1/inspections/LGA-2026-99999/evaluate").status_code == 404
    assert client.get("/api/v1/inspections/LGA-2026-99999/evaluation").status_code == 404


def test_evaluation_not_run_yet_404(stub_cv, stub_ai, real_legal_engine, client):
    inspection_id = upload(client).json()["inspection_id"]
    response = client.get(f"/api/v1/inspections/{inspection_id}/evaluation")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EVALUATION_NOT_FOUND"


def _settings():
    from app.config import get_settings

    return get_settings()


# M/N. persistence + versioning --------------------------------------------------


def test_evaluation_persists_and_reloads(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _MINIMAL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    first = _evaluate(client, inspection_id)
    # Survives a full retrieval round-trip (fresh API call, persisted rows).
    via_get = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    assert via_get["evaluation_id"] == first["evaluation_id"]
    assert via_get["results"] == first["results"]
    # GET inspection embeds the same evaluation.
    assert client.get(f"/api/v1/inspections/{inspection_id}").json()["evaluation"]["evaluation_id"] == first["evaluation_id"]


def test_reevaluation_appends_a_new_version(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _MINIMAL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    first = _evaluate(client, inspection_id)
    _use_fields(monkeypatch, _FULL_FIELDS)
    second = _evaluate(client, inspection_id)
    assert second["evaluation_version"] == first["evaluation_version"] + 1
    assert second["evaluation_id"] != first["evaluation_id"]
    # Both versions coexist; version 1's persisted rule rows are exactly what
    # the first run returned — the original automated result is immutable.
    import app.database as database
    from app.models.inspection import InspectionEvaluation
    from app.services import evaluation_service

    with database.SessionLocal() as session:
        evaluations = (
            session.query(InspectionEvaluation)
            .order_by(InspectionEvaluation.evaluation_version)
            .all()
        )
        assert [e.evaluation_version for e in evaluations] == [1, 2]
        version_one = evaluation_service.evaluation_out(evaluations[0])
    assert {r["rule_id"]: r["status"] for r in version_one["results"]} == {
        r["rule_id"]: r["status"] for r in first["results"]
    }
    # Latest retrieval shows version 2 only.
    reloaded = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    assert reloaded["evaluation_version"] == 2
    assert reloaded["evaluation_id"] == second["evaluation_id"]


# O. no score, no certification --------------------------------------------------


def test_no_score_and_no_certification_language(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _use_fields(monkeypatch, _FULL_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    body = str(_evaluate(client, inspection_id)).lower()
    for forbidden in ("score", "certif", "legally compliant", "government approved"):
        assert forbidden not in body
    # Per-rule confidences are engine-produced, never rolled up.
    evaluation = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    assert "overall_confidence" not in str(evaluation).lower()
