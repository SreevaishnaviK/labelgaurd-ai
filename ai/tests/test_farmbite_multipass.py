"""Phase 9B: FarmBite regression over the multi-pass OCR fixture.

The base fixture (farmbite_ocr.json) is pass A alone. This fixture carries
the REAL merged state of the same label after the recovery pass — `Net
Weight:` and `52g` were erased by pass A's thresholding and read at 96%
confidence by the contrast-only pass B. Extraction must produce the net
quantity from those recovery blocks, keep every other field exactly as
before, and bind evidence to the (namespaced) recovery block ids.
"""
import json
from pathlib import Path

import pytest

from app.extraction.deterministic import DeterministicFieldExtractor
from app.schemas.extraction import OCRBlockIn, OCRPageIn

FIXTURE = Path(__file__).parent / "fixtures" / "farmbite_ocr_multipass.json"


def _page() -> list[OCRPageIn]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        OCRPageIn(
            page_number=1,
            width=data["page"]["width"],
            height=data["page"]["height"],
            full_text=data["page"]["full_text"],
            blocks=[OCRBlockIn(**b) for b in data["blocks"]],
        )
    ]


@pytest.fixture(scope="module")
def fields() -> dict[str, dict]:
    out = DeterministicFieldExtractor().extract_fields(_page())
    return {f.field_name: f.model_dump() for f in out}


# ---------------------------------------------------------------- the recovery

def test_net_quantity_from_recovery_blocks(fields):
    field = fields["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 52.0, "unit": "g"}


def test_net_quantity_evidence_references_recovery_blocks(fields):
    """Evidence binds to the actual pass-B blocks carrying the declaration."""
    field = fields["net_quantity"]
    evidence_ids = {e["ocr_block_id"] for e in field["evidence"]}
    assert "block_b041" in evidence_ids or "block_b043" in evidence_ids


def test_recovery_blocks_carry_pass_provenance():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    recovery = [b for b in data["blocks"] if b["source_pass"] == "B"]
    assert recovery, "fixture must contain recovery blocks"
    assert all(b["id"].startswith("block_b") for b in recovery)


def test_no_duplicate_block_ids_in_merged_fixture():
    """§15: merged output must not duplicate ids — one block per detection."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ids = [b["id"] for b in data["blocks"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- unchanged fields

def test_manufacturer_unchanged(fields):
    assert fields["manufacturer"]["value"] == {"name": "FarmBite Foods Pvt. Ltd."}


def test_packer_unchanged(fields):
    assert fields["packer"]["value"] == {"name": "FarmBite Foods Pvt. Ltd."}


def test_address_unchanged(fields):
    assert fields["manufacturer_address"]["value"]["address"] == (
        "Plot No. 42, Food Park, Sector 8, Greater Noida, Uttar Pradesh - 201306, India."
    )


def test_mrp_unchanged(fields):
    assert fields["mrp"]["value"] == {"amount": 30.0, "currency": "INR"}


def test_batch_unchanged(fields):
    assert fields["batch_number"]["value"]["batch"] == "FB0524"


def test_manufacturing_date_unchanged(fields):
    assert fields["manufacturing_date"]["value"]["date"] == "15 MAY 2024"


def test_use_by_unchanged(fields):
    assert fields["use_by"]["value"]["date"] == "15 NOV 2024"


def test_ingredients_unchanged(fields):
    assert fields["ingredients"]["value"]["ingredients"] == (
        "Potatoes, Edible Vegetable Oil (Palmolein), Iodised Salt."
    )


def test_product_name_unchanged(fields):
    assert fields["product_name"]["value"]["name"] == "POTATO CHIPS CLASSIC SALTED"


def test_country_of_origin_stays_not_detected(fields):
    """The address tail must still not become a country declaration."""
    assert fields["country_of_origin"]["status"] == "not_detected"


def test_no_nutrition_value_becomes_net_quantity(fields):
    """Even with nutrition numbers everywhere, the net quantity is the
    declared 52 g — never 6.5/53.0/34.0/650 from the panel."""
    assert fields["net_quantity"]["value"] == {"value": 52.0, "unit": "g"}
