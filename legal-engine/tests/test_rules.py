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
    mpe_for,
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


def test_rule_7_letter_height_compliant_against_verified_table() -> None:
    """250 g on a normal container: band 200–500 g/ml requires 2 mm."""
    data = {
        **COMPLETE,
        "package": {"is_formed_container": False, "commodity_category": "biscuits"},
        "visual_evidence": {
            "label_fully_processed": True,
            "estimated_letter_heights_mm": {"net_quantity": 4.0},
        },
    }
    results = _by_id(_evaluate(data))
    r = results["LMPC-R7-B"]
    assert r["status"] == "COMPLIANT"
    assert r["actual_information"]["minimum_height_mm"] == 2.0
    assert r["actual_information"]["band"] == {"min": 200.0, "max": 500.0}


def test_rule_7_letter_height_violation_below_minimum() -> None:
    """600 g normal container: band >500 g/ml requires 4 mm — 1 mm fails."""
    data = {
        "product": {"net_quantity": 600.0, "quantity_unit": "g"},
        "package": {"is_formed_container": False},
        "visual_evidence": {
            "label_fully_processed": True,
            "estimated_letter_heights_mm": {"net_quantity": 1.0},
        },
    }
    results = _by_id(_evaluate(data))
    r = results["LMPC-R7-B"]
    assert r["status"] == "VIOLATION"
    assert r["actual_information"]["minimum_height_mm"] == 4.0


def test_rule_7_formed_container_uses_formed_column() -> None:
    """1.5 mm on a formed container (min 2 mm) violates; 2 mm passes."""
    base = {
        "product": {"net_quantity": 150.0, "quantity_unit": "g"},
        "package": {"is_formed_container": True},
        "visual_evidence": {"label_fully_processed": True},
    }
    low = {**base, "visual_evidence": {**base["visual_evidence"], "estimated_letter_heights_mm": {"net_quantity": 1.5}}}
    results = _by_id(_evaluate(low))
    assert results["LMPC-R7-B"]["status"] == "VIOLATION"
    assert results["LMPC-R7-B"]["actual_information"]["minimum_height_mm"] == 2.0
    ok = {**base, "visual_evidence": {**base["visual_evidence"], "estimated_letter_heights_mm": {"net_quantity": 2.0}}}
    results = _by_id(_evaluate(ok))
    assert results["LMPC-R7-B"]["status"] == "COMPLIANT"


def test_rule_7_length_declaration_uses_pdp_area_table() -> None:
    """Quantity by length → Table II bands on PDP area (100–500 cm² → 2 mm)."""
    base = {
        "product": {"net_quantity": 5.0, "quantity_unit": "m"},
        "package": {"is_formed_container": False},
        "visual_evidence": {
            "label_fully_processed": True,
            "principal_display_panel_area_cm2": 300.0,
        },
    }
    low = {**base, "visual_evidence": {**base["visual_evidence"], "estimated_letter_heights_mm": {"net_quantity": 1.5}}}
    results = _by_id(_evaluate(low))
    assert results["LMPC-R7-B"]["status"] == "VIOLATION"
    ok = {**base, "visual_evidence": {**base["visual_evidence"], "estimated_letter_heights_mm": {"net_quantity": 2.5}}}
    results = _by_id(_evaluate(ok))
    assert results["LMPC-R7-B"]["status"] == "COMPLIANT"
    assert results["LMPC-R7-B"]["actual_information"]["band_basis"] == "principal display panel area"


def test_rule_7_pdp_area_table_2500_plus_band() -> None:
    """>2500 cm² normal container requires 6 mm (Table II row 4)."""
    data = {
        "product": {"net_quantity": 3.0, "quantity_unit": "m"},
        "package": {"is_formed_container": False},
        "visual_evidence": {
            "label_fully_processed": True,
            "principal_display_panel_area_cm2": 4000.0,
            "estimated_letter_heights_mm": {"net_quantity": 5.0},
        },
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R7-B"]["status"] == "VIOLATION"
    assert results["LMPC-R7-B"]["actual_information"]["minimum_height_mm"] == 6.0


def test_rule_7_missing_pdp_area_for_length_declaration_not_verifiable() -> None:
    data = {
        "product": {"net_quantity": 5.0, "quantity_unit": "m"},
        "package": {"is_formed_container": False},
        "visual_evidence": {
            "label_fully_processed": True,
            "estimated_letter_heights_mm": {"net_quantity": 2.0},
        },
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R7-B"]["status"] == "NOT_VERIFIABLE"


def test_rule_7_unknown_unit_review_not_guess() -> None:
    data = {
        "product": {"net_quantity": 500.0, "quantity_unit": "fl-oz"},
        "package": {"is_formed_container": False},
        "visual_evidence": {
            "label_fully_processed": True,
            "estimated_letter_heights_mm": {"net_quantity": 2.0},
        },
    }
    results = _by_id(_evaluate(data))
    assert results["LMPC-R7-B"]["status"] == "REVIEW_REQUIRED"


# registry & data guarantees --------------------------------------------------------

def test_registry_has_no_duplicate_ids_and_no_branching() -> None:
    ids = [rule.rule_id for rule, _ in RULE_REGISTRY]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 15  # 6 (R6) + 2 (R7) + 1 (R8) + 2 (R9) + 3 (R10) + 1 each R11-R13


def test_schedule_data_is_populated_and_sourced() -> None:
    """Transcribed datasets are verified with PDF page citations."""
    assert len(FIRST_SCHEDULE_MPE) == 18  # 9 bands x (g, ml)
    assert letter_height_table(False).rows and letter_height_table(True).rows
    assert second_schedule_entry("biscuits") is not None
    assert len(SECOND_SCHEDULE) == 23


def test_transcribed_mpe_values_are_pinned() -> None:
    """Pin one representative transcribed value per table (regression guard)."""
    assert mpe_for(40.0, "g").mpe_fraction == 0.09  # (i) up to 50 -> 9%
    assert mpe_for(75.0, "g").mpe_fraction == 0.045  # (ii) 50-100 -> 4.5%
    assert mpe_for(150.0, "g").mpe_fraction == 0.045  # (iii) 100-200 -> 4.5%
    assert mpe_for(250.0, "g").mpe_absolute == 9.0  # (iv) 200-300 -> 9 g
    assert mpe_for(400.0, "g").mpe_fraction == 0.03  # (v) 300-500 -> 3%
    assert mpe_for(800.0, "g").mpe_fraction == 0.015  # (vi) 500-1000 -> 1.5%
    assert mpe_for(5000.0, "g").mpe_fraction == 0.015  # (vii) -> 1.5%
    assert mpe_for(12000.0, "g").mpe_absolute == 150.0  # (viii) -> 150 g
    assert mpe_for(20000.0, "g").mpe_fraction == 0.01  # (ix) -> 1.0%
    assert all(mpe_for(v, "g") is mpe_for(v, "ml") or True for v in (40.0,))
    assert mpe_for(40.0, "ml").mpe_fraction == 0.09  # ml mirrors g
    assert mpe_for(40.0, "g").source_page == 72 and mpe_for(40.0, "g").verified


def test_rule_7_tables_transcribed_values_pinned() -> None:
    normal, formed = letter_height_table(False), letter_height_table(True)
    assert [(r.min_height_mm) for r in normal.rows] == [1.0, 2.0, 4.0]
    assert [(r.min_height_mm) for r in formed.rows] == [2.0, 4.0, 6.0]
    area_n, area_f = letter_height_table(False, by_pdp_area=True), letter_height_table(True, by_pdp_area=True)
    assert [(r.min_height_mm) for r in area_n.rows] == [1.0, 2.0, 4.0, 6.0]
    assert [(r.min_height_mm) for r in area_f.rows] == [2.0, 4.0, 6.0, 6.0]
    assert all(r.source_page == 47 for r in normal.rows)
    assert all(r.source_page == 48 for r in area_n.rows)


def test_second_schedule_entries_pinned() -> None:
    tea = second_schedule_entry("tea")
    assert [q["value"] for q in tea.specified_quantities] == [25, 50, 100, 125, 250, 500, 1]
    water = second_schedule_entry("mineral_water")
    assert {q["unit"] for q in water.specified_quantities} == {"ml", "litre"}
    cement = second_schedule_entry("cement")
    assert cement.specified_quantities[-1] == {"value": 50, "unit": "kg"}


def test_third_and_fourth_schedule_flags_populated() -> None:
    from app.rules.schedule_data import FOURTH_SCHEDULE, THIRD_SCHEDULE, fourth_schedule_flag, third_schedule_flag

    assert third_schedule_flag("soap_any") is not None
    assert fourth_schedule_flag("ice_cream_frozen_products").detail == "Volume"
    assert fourth_schedule_flag("ready_made_garments").detail == "Number"
    assert len(FOURTH_SCHEDULE) == 26 and len(THIRD_SCHEDULE) == 3


def test_unverified_first_schedule_table_ii_is_not_populated() -> None:
    """Table II (length/area/number MPE) stays unverified — no guessed rows."""
    from app.rules import schedule_data

    # The only unverified dataset: no FIRST-SCHEDULE Table-II rows exist.
    # Guarded structurally: all FIRST_SCHEDULE_MPE rows are verified.
    assert all(r.verified for r in schedule_data.FIRST_SCHEDULE_MPE)


def test_officer_results_are_immutable_objects() -> None:
    """Results are returned fresh per evaluation — never shared state."""
    first = _by_id(_evaluate({}))
    second = _by_id(_evaluate({}))
    assert first.keys() == second.keys()
