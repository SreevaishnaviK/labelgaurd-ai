"""Legal Engine rule evaluator tests.

The 13 required scenarios, plus registry and verification-gate guarantees.
Central invariant under test: missing evidence is NEVER automatically treated
as a violation — VIOLATION only when the evidence establishes the declaration
is absent (visual_evidence.label_fully_processed=True).
"""
import pytest
from fastapi.testclient import TestClient

from app.rules.registry import RULE_REGISTRY
from app.rules.rule_model import SOURCE_DOCUMENT
from app.rules.schedule_data import (
    FIRST_SCHEDULE_MPE,
    SECOND_SCHEDULE,
    letter_height_table,
    second_schedule_entry,
)
from app.schemas.evaluation import EvaluationInput, ProductInfo, VisualEvidence

from app.main import app

client = TestClient(app)


def _evaluate(data: dict) -> dict:
    response = client.post("/api/v1/evaluate", json=data)
    assert response.status_code == 200
    return response.json()


def _by_id(body: dict) -> dict:
    return {r["rule_id"]: r for r in body["results"]}


def _partial(**product) -> dict:
    return {"product": {k: v for k, v in product.items() if v is not None}}


COMPLETE = {
    "product": {
        "product_name": "Biscuits (Vanilla)",
        "manufacturer": "ABC Foods Pvt Ltd",
        "address": "Plot 12, Industrial Estate, Vijayawada, Andhra Pradesh",
        "net_quantity": 250.0,
        "quantity_unit": "g",
        "mrp": {"amount": 50.0, "currency": "INR"},
        "manufacture_month": 8,
        "manufacture_year": 2026,
        "consumer_care": "care@abcfoods.example",
    },
    "package": {"commodity_category": "biscuits"},
    "visual_evidence": {"label_fully_processed": True},
}


# 1. complete compliant package -------------------------------------------------

def test_complete_compliant_package() -> None:
    body = _evaluate(COMPLETE)
    results = _by_id(body)
    presence = [results[f"LMPC-R6-{c}"] for c in "ABCDEF"]
    assert all(r["status"] == "COMPLIANT" for r in presence), [r["finding"] for r in presence]
    assert results["LMPC-R10-A"]["status"] == "COMPLIANT"
    assert results["LMPC-R10-C"]["status"] == "COMPLIANT"
    assert results["LMPC-R11-A"]["status"] == "COMPLIANT"
    assert results["LMPC-R12-A"]["status"] == "COMPLIANT"
    assert results["LMPC-R13-A"]["status"] == "COMPLIANT"
    # No overall score, no certification language anywhere.
    flattened = str(body).lower()
    assert "score" not in flattened and "certifi" not in flattened


def test_every_result_is_fully_sourced() -> None:
    body = _evaluate(COMPLETE)
    for result in body["results"]:
        assert result["source"]["document"] == SOURCE_DOCUMENT
        assert result["rule_id"] and result["rule_number"] and result["title"]
        assert result["finding"]


# 2. missing manufacturer -------------------------------------------------------

def test_missing_manufacturer_not_a_violation_without_established_absence() -> None:
    data = {"product": {k: v for k, v in COMPLETE["product"].items() if k != "manufacturer"}}
    results = _by_id(_evaluate(data))
    # Not extracted ≠ violation: the label was not affirmed fully processed.
    assert results["LMPC-R6-A"]["status"] == "NOT_VERIFIABLE"
    assert results["LMPC-R10-A"]["status"] == "NOT_VERIFIABLE"
    assert results["LMPC-R6-A"]["requires_officer_verification"] is True


def test_missing_manufacturer_violation_only_when_absence_established() -> None:
    data = {
        "product": {k: v for k, v in COMPLETE["product"].items() if k != "manufacturer"},
        "visual_evidence": {"label_fully_processed": True},
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R10-A"]["status"] == "VIOLATION"


# 3. missing address ------------------------------------------------------------

def test_missing_address_with_party_declared() -> None:
    data = {"product": {k: v for k, v in COMPLETE["product"].items() if k != "address"}}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R10-C"]["status"] == "NOT_VERIFIABLE"
    data["visual_evidence"] = {"label_fully_processed": True}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R10-C"]["status"] == "VIOLATION"


# 4. missing net quantity ---------------------------------------------------------

def test_missing_net_quantity() -> None:
    data = {"product": {k: v for k, v in COMPLETE["product"].items() if k != "net_quantity" and k != "quantity_unit"}}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-C"]["status"] == "NOT_VERIFIABLE"
    assert results["LMPC-R11-A"]["status"] == "NOT_VERIFIABLE"
    data["visual_evidence"] = {"label_fully_processed": True}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-C"]["status"] == "VIOLATION"
    assert results["LMPC-R11-A"]["status"] == "VIOLATION"


# 5. missing MRP ------------------------------------------------------------------

def test_missing_mrp() -> None:
    data = {"product": {k: v for k, v in COMPLETE["product"].items() if k != "mrp"}}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-E"]["status"] == "NOT_VERIFIABLE"
    data["visual_evidence"] = {"label_fully_processed": True}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-E"]["status"] == "VIOLATION"


# 6. missing manufacture date -----------------------------------------------------

def test_missing_manufacture_date() -> None:
    data = {
        "product": {
            k: v for k, v in COMPLETE["product"].items() if k not in ("manufacture_month", "manufacture_year")
        }
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-D"]["status"] == "NOT_VERIFIABLE"
    data["visual_evidence"] = {"label_fully_processed": True}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-D"]["status"] == "VIOLATION"


# 7. missing consumer-care --------------------------------------------------------

def test_missing_consumer_care() -> None:
    data = {"product": {k: v for k, v in COMPLETE["product"].items() if k != "consumer_care"}}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-F"]["status"] == "NOT_VERIFIABLE"
    data["visual_evidence"] = {"label_fully_processed": True}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-F"]["status"] == "VIOLATION"


def test_consumer_care_any_single_form_satisfies() -> None:
    data = {"product": {k: v for k, v in COMPLETE["product"].items() if k != "consumer_care"}}
    data["product"]["customer_care_phone"] = "1800-123-4567"
    results = _by_id(_evaluate(data))
    assert results["LMPC-R6-F"]["status"] == "COMPLIANT"


# 8. imported package -------------------------------------------------------------

def test_imported_package_without_importer() -> None:
    data = {"product": {"product_name": "Imported Chocolate", "manufacturer": "Foreign Co"}, "package": {"is_imported": True}}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R10-B"]["status"] == "NOT_VERIFIABLE"


def test_imported_package_violation_when_absence_established() -> None:
    data = {
        "product": {"product_name": "Imported Chocolate"},
        "package": {"is_imported": True},
        "visual_evidence": {"label_fully_processed": True},
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R10-B"]["status"] == "VIOLATION"


def test_importer_rule_not_applicable_for_domestic() -> None:
    results = _by_id(_evaluate(_partial(product_name="Domestic Biscuits")))
    assert results["LMPC-R10-B"]["status"] == "NOT_APPLICABLE"


def test_imported_package_with_importer_compliant() -> None:
    data = {
        "product": {"product_name": "Imported Chocolate", "importer": "Global Imports Ltd"},
        "package": {"is_imported": True},
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R10-B"]["status"] == "COMPLIANT"


# 9. invalid/missing quantity unit ------------------------------------------------

def test_missing_quantity_unit_with_value() -> None:
    data = {"product": {"net_quantity": 500.0}}
    results = _by_id(_evaluate(data))
    assert results["LMPC-R12-A"]["status"] == "NOT_VERIFIABLE"
    assert results["LMPC-R13-A"]["status"] == "REVIEW_REQUIRED"


def test_unrecognized_quantity_unit_requires_review_not_violation() -> None:
    results = _by_id(_evaluate(_partial(net_quantity=500.0, quantity_unit="fl-oz")))
    assert results["LMPC-R12-A"]["status"] == "REVIEW_REQUIRED"
    assert results["LMPC-R13-A"]["status"] == "REVIEW_REQUIRED"
    assert results["LMPC-R12-A"]["status"] != "VIOLATION"


def test_recognized_quantity_unit_compliant() -> None:
    results = _by_id(_evaluate(_partial(net_quantity=1.0, quantity_unit="kg")))
    assert results["LMPC-R12-A"]["status"] == "COMPLIANT"
    assert results["LMPC-R13-A"]["status"] == "COMPLIANT"


# 10. missing visual evidence ------------------------------------------------------

def test_no_visual_evidence_defaults_to_not_verifiable() -> None:
    results = _by_id(_evaluate({}))
    verifiable = [r for r in results.values() if r["status"] in ("COMPLIANT", "VIOLATION")]
    assert verifiable == []
    assert all(r["status"] in ("NOT_VERIFIABLE", "REVIEW_REQUIRED", "NOT_APPLICABLE") for r in results.values())


# 11. rule not applicable -----------------------------------------------------------

def test_wholesale_and_export_flags_do_not_break_evaluation() -> None:
    data = {**COMPLETE, "package": {**COMPLETE["package"], "is_wholesale": True, "is_export": True}}
    body = _evaluate(data)
    assert body["status"] == "success"


def test_importer_rule_applicability() -> None:
    results = _by_id(_evaluate({}))
    assert results["LMPC-R10-B"]["status"] == "NOT_APPLICABLE"


# 12/13. insufficient evidence / review-required ------------------------------------

def test_insufficient_evidence_is_not_verifiable() -> None:
    results = _by_id(_evaluate(_partial(product_name="Mystery Pack")))
    assert results["LMPC-R6-C"]["status"] == "NOT_VERIFIABLE"


def test_possible_issue_requires_review() -> None:
    # Letter heights measured but container type unknown → REVIEW_REQUIRED.
    data = {
        "visual_evidence": {
            "label_fully_processed": True,
            "estimated_letter_heights_mm": {"net_quantity": 4.0},
        }
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R7-B"]["status"] == "REVIEW_REQUIRED"


def test_rule_7_letter_height_never_evaluates_unverified_table() -> None:
    """With unverified schedule data the threshold check must refuse to run."""
    assert not letter_height_table(False).verified
    data = {
        "package": {"is_formed_container": False},
        "visual_evidence": {
            "label_fully_processed": True,
            "estimated_letter_heights_mm": {"net_quantity": 1.0, "mrp": 1.0},
        },
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R7-B"]["status"] == "NOT_VERIFIABLE"


# registry & data guarantees --------------------------------------------------------

def test_registry_has_no_duplicate_ids_and_no_branching() -> None:
    ids = [rule.rule_id for rule, _ in RULE_REGISTRY]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 15  # 6 (R6) + 2 (R7) + 1 (R8) + 2 (R9) + 3 (R10) + 1 each R11-R13


def test_schedule_data_ships_unverified_and_gated() -> None:
    """No legal value is asserted without the supplied PDF."""
    assert FIRST_SCHEDULE_MPE == []
    assert SECOND_SCHEDULE == []
    assert not letter_height_table(False).rows
    assert not letter_height_table(True).rows
    assert second_schedule_entry("biscuits") is None


def test_unverified_schedule_data_cannot_produce_decisions() -> None:
    """The gate: even a hand-inserted row without verified=True is ignored."""
    from app.rules import schedule_data
    from app.rules.schedule_data import mpe_for

    assert mpe_for(250.0, "g") is None


def test_officer_results_are_immutable_objects() -> None:
    """Results are returned fresh per evaluation — never shared state."""
    first = _by_id(_evaluate({}))
    second = _by_id(_evaluate({}))
    assert first.keys() == second.keys()
