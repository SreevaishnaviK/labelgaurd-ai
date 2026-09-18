"""Backend Phase 8 tests: officer verification over immutable automated results.

The legal engine runs as the REAL service (shared fixture). Central
invariants under test: RuleEvaluation rows are never modified by officer
decisions, overrides require a comment, effective status is backend-derived,
audit history is append-only, and verifications bind to the exact evaluation
version they reviewed.
"""
from .conftest import upload

# Minimal detected-field set that produces a real evaluation with a mixture
# of statuses (MRP-only: R6-E compliant, R11-B not verifiable, etc.).
_MRP_FIELDS = [
    {
        "field_name": "mrp", "status": "detected",
        "value": {"amount": 68.0, "currency": "INR"}, "raw_text": "MRP ₹68.00",
        "ocr_confidence": 96.4, "extraction_confidence": 98.0, "method": "deterministic",
        "evidence": [{"ocr_block_id": "block_005", "page_number": 1}],
    },
]


def _setup(client, monkeypatch, fields):
    from . import conftest as _conftest

    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: fields)
    inspection_id = upload(client).json()["inspection_id"]
    response = client.post(f"/api/v1/inspections/{inspection_id}/evaluate")
    assert response.status_code == 200, response.text
    return inspection_id, response.json()


def _rule(evaluation, rule_id):
    return next(r for r in evaluation["results"] if r["rule_id"] == rule_id)


def _verify(client, inspection_id, rule_evaluation_id, decision, comment=None, **extra):
    payload = {"rule_evaluation_id": rule_evaluation_id, "decision": decision, **extra}
    if comment is not None:
        payload["comment"] = comment
    return client.post(f"/api/v1/inspections/{inspection_id}/verifications", json=payload)


# A/B: accept + confirm paths ----------------------------------------------------


def test_accept_compliant_rule(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R6-E")  # MRP detected -> COMPLIANT
    assert rule["status"] == "COMPLIANT"

    response = _verify(client, inspection_id, rule["rule_evaluation_id"], "ACCEPT", "Matches package.")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] == "ACCEPT"
    assert body["officer_identifier"]

    fetched = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    verified = _rule(fetched, "LMPC-R6-E")
    assert verified["effective_status"] == "COMPLIANT"  # ACCEPT keeps automated
    assert verified["officer_verification"]["decision"] == "ACCEPT"


def test_confirm_not_verifiable_rule(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R11-B")  # MRP-only: no quantity -> NOT_VERIFIABLE
    assert rule["status"] == "NOT_VERIFIABLE"

    response = _verify(
        client, inspection_id, rule["rule_evaluation_id"], "CONFIRM_NOT_VERIFIABLE",
        "Manual check pending; quantity not readable in this render.",
    )
    assert response.status_code == 201, response.text
    fetched = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    assert _rule(fetched, "LMPC-R11-B")["effective_status"] == "NOT_VERIFIABLE"


def test_confirm_decision_must_match_automated_status(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R6-E")  # COMPLIANT
    response = _verify(client, inspection_id, rule["rule_evaluation_id"], "CONFIRM_REVIEW_REQUIRED")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DECISION_CONFLICT"


# C/D: overrides -----------------------------------------------------------------


def test_override_compliant_and_violation(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    good = _rule(evaluation, "LMPC-R6-E")   # COMPLIANT
    unverifiable = _rule(evaluation, "LMPC-R11-B")  # NOT_VERIFIABLE

    response = _verify(
        client, inspection_id, unverifiable["rule_evaluation_id"], "OVERRIDE_COMPLIANT",
        "Physical label inspected manually; declaration is clearly visible.",
    )
    assert response.status_code == 201, response.text

    response = _verify(
        client, inspection_id, good["rule_evaluation_id"], "OVERRIDE_VIOLATION",
        "Printed MRP does not match the invoice for this batch.",
    )
    assert response.status_code == 201, response.text

    fetched = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    assert _rule(fetched, "LMPC-R11-B")["effective_status"] == "COMPLIANT"
    assert _rule(fetched, "LMPC-R6-E")["effective_status"] == "VIOLATION"
    # Overall effective rollup moves with the override — backend-derived.
    assert fetched["officer_effective_status"] == "NON_COMPLIANT"
    # ...while the automated rollup is untouched.
    assert fetched["overall_status"] == evaluation["overall_status"]


# E: override comment required ---------------------------------------------------


def test_override_without_comment_rejected(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R6-E")
    for comment in (None, "", "   "):
        response = _verify(client, inspection_id, rule["rule_evaluation_id"], "OVERRIDE_COMPLIANT", comment)
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "COMMENT_REQUIRED"
    # No verification row was created by the failed attempts.
    assert client.get(f"/api/v1/inspections/{inspection_id}/verifications").json() == []


# F/G/H: originals immutable -----------------------------------------------------


def test_original_rule_evaluation_unchanged(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R11-B")
    original = dict(rule)

    _verify(
        client, inspection_id, rule["rule_evaluation_id"], "OVERRIDE_COMPLIANT",
        "Verified directly on the physical package.",
    )

    fetched = _rule(client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json(), "LMPC-R11-B")
    for key in ("status", "finding", "confidence", "source", "evidence", "severity"):
        assert fetched[key] == original[key], f"automated {key} mutated"
    # Automated top-level rollup untouched too.
    assert (
        client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()["overall_status"]
        == evaluation["overall_status"]
    )


# I/J: effective status ----------------------------------------------------------


def test_no_verification_effective_equals_automated(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    fetched = client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json()
    for result in fetched["results"]:
        assert result["effective_status"] == result["status"]
        assert result["officer_verification"] is None
    assert fetched["officer_effective_status"] == fetched["overall_status"]


# K/L: audit log -----------------------------------------------------------------


def test_audit_log_created_and_append_only(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R11-B")

    _verify(client, inspection_id, rule["rule_evaluation_id"], "CONFIRM_NOT_VERIFIABLE", "First look.")
    _verify(
        client, inspection_id, rule["rule_evaluation_id"], "OVERRIDE_COMPLIANT",
        "Second look: declaration clearly present.",
    )

    log = client.get(f"/api/v1/inspections/{inspection_id}/audit-log").json()
    officer_entries = [e for e in log if e["action"] == "RULE_VERIFICATION"]
    assert len(officer_entries) == 2
    assert officer_entries[0]["decision"] == "CONFIRM_NOT_VERIFIABLE"
    assert officer_entries[0]["previous_state"] == "NOT_VERIFIABLE"
    assert officer_entries[1]["decision"] == "OVERRIDE_COMPLIANT"
    # Oldest first: append-only ordering.
    assert officer_entries[0]["id"] < officer_entries[1]["id"]
    assert all(e["actor"] for e in officer_entries)


# M/N: evaluation versioning -----------------------------------------------------


def test_verification_binds_to_evaluation_version(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation_v1 = _setup(client, monkeypatch, _MRP_FIELDS)
    rule_v1 = _rule(evaluation_v1, "LMPC-R11-B")
    v1_pk = rule_v1["rule_evaluation_id"]

    _verify(
        client, inspection_id, v1_pk, "OVERRIDE_COMPLIANT",
        "Verified against the physical package.",
    )

    # Re-evaluate: new immutable version, old verification does NOT attach.
    evaluation_v2 = client.post(f"/api/v1/inspections/{inspection_id}/evaluate").json()
    assert evaluation_v2["evaluation_version"] == evaluation_v1["evaluation_version"] + 1
    rule_v2 = _rule(evaluation_v2, "LMPC-R11-B")
    assert rule_v2["rule_evaluation_id"] != v1_pk
    assert rule_v2["officer_verification"] is None
    assert rule_v2["effective_status"] == "NOT_VERIFIABLE"

    # And the v1 verification record still exists, still bound to v1.
    verifications = client.get(f"/api/v1/inspections/{inspection_id}/verifications").json()
    assert len(verifications) == 1
    assert verifications[0]["rule_evaluation_id"] == v1_pk
    assert verifications[0]["evaluation_id"] == evaluation_v1["evaluation_id"]


# O: history preserved -----------------------------------------------------------


def test_multiple_verifications_preserve_history(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R11-B")
    pk = rule["rule_evaluation_id"]

    _verify(client, inspection_id, pk, "CONFIRM_NOT_VERIFIABLE", "Pending physical check.")
    _verify(
        client, inspection_id, pk, "OVERRIDE_COMPLIANT",
        "Manual inspection confirms the declaration.",
    )

    verifications = client.get(f"/api/v1/inspections/{inspection_id}/verifications").json()
    assert len(verifications) == 2
    # Latest first in the listing; latest is the effective decision.
    assert verifications[0]["decision"] == "OVERRIDE_COMPLIANT"
    fetched = _rule(client.get(f"/api/v1/inspections/{inspection_id}/evaluation").json(), "LMPC-R11-B")
    assert fetched["effective_status"] == "COMPLIANT"


# P: cross-inspection references rejected ----------------------------------------


def test_cross_inspection_rule_reference_rejected(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    _inspection_a, evaluation_a = _setup(client, monkeypatch, _MRP_FIELDS)
    rule_a = _rule(evaluation_a, "LMPC-R6-E")

    from . import conftest as _conftest

    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _MRP_FIELDS)
    inspection_b = upload(client).json()["inspection_id"]
    evaluation_b = client.post(f"/api/v1/inspections/{inspection_b}/evaluate").json()

    # Inspection B tries to verify inspection A's rule evaluation.
    response = _verify(
        client, inspection_b, rule_a["rule_evaluation_id"], "OVERRIDE_COMPLIANT",
        "This should never be allowed.",
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "EVALUATION_MISMATCH"
    # B's own evaluation is unaffected and unverified.
    assert _rule(evaluation_b, "LMPC-R6-E")["officer_verification"] is None


# Q/R/S: field verification ------------------------------------------------------


def test_field_verification_preserves_original_value(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    from . import conftest as _conftest

    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _MRP_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    inspection = client.get(f"/api/v1/inspections/{inspection_id}").json()
    field = next(f for f in inspection["extraction"]["fields"] if f["field_name"] == "mrp")
    original_value = dict(field["value"])

    response = client.post(
        f"/api/v1/inspections/{inspection_id}/field-verifications",
        json={
            "extracted_field_id": field["extracted_field_id"],
            "verification_status": "verified",
            "comment": "Confirmed from package.",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["verification_status"] == "verified"

    # Original extraction untouched after reload (S: refresh persistence).
    reloaded = client.get(f"/api/v1/inspections/{inspection_id}").json()
    field_after = next(f for f in reloaded["extraction"]["fields"] if f["field_name"] == "mrp")
    assert field_after["value"] == original_value
    # The verification rides beside it.
    assert len(reloaded["field_verifications"]) == 1
    assert reloaded["field_verifications"][0]["field_name"] == "mrp"
    assert reloaded["field_verifications"][0]["officer_identifier"]


def test_field_correction_records_verified_value(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    from . import conftest as _conftest

    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _MRP_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    inspection = client.get(f"/api/v1/inspections/{inspection_id}").json()
    field = next(f for f in inspection["extraction"]["fields"] if f["field_name"] == "mrp")

    response = client.post(
        f"/api/v1/inspections/{inspection_id}/field-verifications",
        json={
            "extracted_field_id": field["extracted_field_id"],
            "verification_status": "corrected",
            "verified_value": {"amount": 72.0, "currency": "INR"},
            "comment": "Package shows ₹72.00; OCR misread the last digit.",
        },
    )
    assert response.status_code == 201, response.text

    reloaded = client.get(f"/api/v1/inspections/{inspection_id}").json()
    field_after = next(f for f in reloaded["extraction"]["fields"] if f["field_name"] == "mrp")
    assert field_after["value"] == {"amount": 68.0, "currency": "INR"}  # original
    verification = reloaded["field_verifications"][0]
    assert verification["verification_status"] == "corrected"
    assert verification["verified_value"] == {"amount": 72.0, "currency": "INR"}

    # Audit entry exists for the field action too.
    log = client.get(f"/api/v1/inspections/{inspection_id}/audit-log").json()
    assert any(e["action"] == "FIELD_VERIFICATION" for e in log)


def test_corrected_field_requires_value(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    from . import conftest as _conftest

    monkeypatch.setattr(_conftest, "_fake_ai_fields", lambda: _MRP_FIELDS)
    inspection_id = upload(client).json()["inspection_id"]
    inspection = client.get(f"/api/v1/inspections/{inspection_id}").json()
    field = next(f for f in inspection["extraction"]["fields"] if f["field_name"] == "mrp")

    response = client.post(
        f"/api/v1/inspections/{inspection_id}/field-verifications",
        json={"extracted_field_id": field["extracted_field_id"], "verification_status": "corrected"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALUE_REQUIRED"


# P2: invalid evidence references rejected ---------------------------------------


def test_invalid_evidence_reference_rejected(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R6-E")
    response = _verify(
        client, inspection_id, rule["rule_evaluation_id"], "ACCEPT", "note",
        evidence_ocr_block_id="block_999",
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EVIDENCE_NOT_FOUND"


def test_unknown_decision_rejected(stub_cv, stub_ai, real_legal_engine, client, monkeypatch):
    inspection_id, evaluation = _setup(client, monkeypatch, _MRP_FIELDS)
    rule = _rule(evaluation, "LMPC-R6-E")
    response = _verify(client, inspection_id, rule["rule_evaluation_id"], "MAKE_IT_COMPLIANT")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_DECISION"
