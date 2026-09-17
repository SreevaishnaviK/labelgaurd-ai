"""Phase 9A regression: FarmBite label extraction via OCR spatial context.

The fixture (tests/fixtures/farmbite_ocr.json) carries REAL Tesseract word
data from the uploaded FarmBite Potato Chips label (LGA-2026-00026), parsed
through the actual CV block parser. On that label the engine interleaves
columns: the manufacturer declaration was fused with its address, the
nutrition table bled into the ingredients, and dates were fragmented. The
deterministic extractor must reconstruct every field from bbox geometry —
and stay honest about what the label does not declare (no country of origin
declaration, no vegetarian text symbol, no OCR-readable net-quantity block
in this render).
"""
import json
from pathlib import Path

import pytest

from app.extraction.deterministic import DeterministicFieldExtractor
from app.schemas.extraction import OCRBlockIn, OCRPageIn

FIXTURE = Path(__file__).parent / "fixtures" / "farmbite_ocr.json"


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
    return {f.field_name: f.model_dump(exclude_none=False) for f in out}


# ------------------------------------------------------------- real-label values

def test_manufacturer_reconstructed_from_interleaved_blocks(fields) -> None:
    assert fields["manufacturer"]["status"] == "detected"
    assert fields["manufacturer"]["value"] == {"name": "FarmBite Foods Pvt. Ltd."}


def test_packer_matches_manufacturer_declaration(fields) -> None:
    assert fields["packer"]["value"] == {"name": "FarmBite Foods Pvt. Ltd."}


def test_address_reconstructed_without_interleaving_artifacts(fields) -> None:
    assert fields["manufacturer_address"]["value"]["address"] == (
        "Plot No. 42, Food Park, Sector 8, Greater Noida, "
        "Uttar Pradesh - 201306, India."
    )


def test_address_excludes_company_name(fields) -> None:
    address = fields["manufacturer_address"]["value"]["address"]
    assert "FarmBite" not in address and "Foods" not in address.split(",")[0]


def test_ingredients_exclude_nutrition_table(fields) -> None:
    value = fields["ingredients"]["value"]["ingredients"]
    assert value == "Potatoes, Edible Vegetable Oil (Palmolein), Iodised Salt."
    for banned in ("Energy", "536", "Protein", "Sodium", "INFORMATION", "NUTRITIONAL"):
        assert banned not in value


def test_mrp_from_anchor_proximity(fields) -> None:
    assert fields["mrp"]["value"] == {"amount": 30.0, "currency": "INR"}


def test_batch_number_not_stolen_from_other_labels(fields) -> None:
    assert fields["batch_number"]["value"] == {"batch": "FB0524"}
    assert "Use" not in fields["batch_number"]["value"]["batch"]


def test_dates_associated_with_fragments(fields) -> None:
    assert fields["manufacturing_date"]["value"] == {"date": "15 MAY 2024"}
    assert fields["use_by"]["value"] == {"date": "15 NOV 2024"}


def test_consumer_care_contacts_in_section_context(fields) -> None:
    assert fields["customer_care_phone"]["value"] == {"phone": "18001234567"}
    assert fields["customer_care_email"]["value"] == {"email": "care@farmbitefoods.com"}


def test_product_name_from_prominent_region(fields) -> None:
    assert fields["product_name"]["value"]["name"] == "POTATO CHIPS CLASSIC SALTED"
    assert "Plot" not in fields["product_name"]["value"]["name"]


# ------------------------------------------------------------- honest absences

def test_country_of_origin_not_inferred_from_address(fields) -> None:
    """'India' appears only inside the manufacturer address — no explicit
    declaration exists, so the field must stay undetected."""
    assert fields["country_of_origin"]["status"] == "not_detected"


def test_vegetarian_not_inferred_from_ingredients(fields) -> None:
    assert fields["vegetarian_non_vegetarian"]["status"] == "not_detected"


def test_net_quantity_absent_from_this_render_is_not_detected(fields) -> None:
    """This OCR render never produced a Net Weight block (front-panel small
    print) — the extractor must not invent one from the nutrition table."""
    assert fields["net_quantity"]["status"] == "not_detected"


def test_brand_name_absent_from_ocr_is_not_fabricated(fields) -> None:
    """'FarmBite' is a stylized logo the OCR cannot read; the name must not
    include it, and nothing may be invented to fill the gap."""
    assert "FarmBite" not in fields["product_name"]["value"]["name"]


def test_every_detected_field_has_real_evidence(fields) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real_ids = {b["id"] for b in data["blocks"]}
    for name, field in fields.items():
        if field["status"] == "detected":
            assert field["evidence"], f"{name} detected without evidence"
            for ref in field["evidence"]:
                assert ref["ocr_block_id"] in real_ids


# ------------------------------------------------------------- §22 negatives

def _block(text: str, block_id: str = "block_001", x: int = 100, y: int = 100, width: int = 400, height: int = 40) -> OCRBlockIn:
    return OCRBlockIn(
        id=block_id, text=text, confidence=96.0, page_number=1,
        bbox={"x": x, "y": y, "width": width, "height": height},
    )


def _extract(*blocks: OCRBlockIn) -> dict[str, dict]:
    page = OCRPageIn(
        page_number=1, width=1920, height=1080,
        full_text="\n".join(b.text for b in blocks), blocks=list(blocks),
    )
    return {f.field_name: f.model_dump(exclude_none=False) for f in DeterministicFieldExtractor().extract_fields([page])}


@pytest.mark.parametrize(
    "text",
    ["per 100g", "536 kcal", "650 mg", "6.5 g", "34.0 g", "PIN 201306"],
)
def test_nutrition_and_pin_values_never_become_net_quantity(text: str) -> None:
    assert _extract(_block(text))["net_quantity"]["status"] == "not_detected"


def test_use_by_label_never_becomes_batch_number() -> None:
    fields = _extract(_block("Use By:", y=100), _block("15 NOV 2024", "block_002", y=145))
    assert fields["batch_number"]["status"] == "not_detected"
    assert fields["use_by"]["value"] == {"date": "15 NOV 2024"}


def test_mrp_never_becomes_batch_number() -> None:
    fields = _extract(_block("MRP \u20b930.00"))
    assert fields["batch_number"]["status"] == "not_detected"


def test_fssai_licence_never_becomes_batch_number() -> None:
    fields = _extract(_block("FSSAI Lic. No. 10018051002634"))
    assert fields["batch_number"]["status"] == "not_detected"


def test_manufacturer_address_never_becomes_product_name() -> None:
    fields = _extract(
        _block("Plot No. 42, Food Park, Sector 8,", y=40, width=800, height=90),
        _block("Greater Noida, Uttar Pradesh - 201306, India.", "block_002", y=140),
    )
    assert fields["product_name"]["status"] == "not_detected"


def test_batch_value_never_becomes_use_by_date() -> None:
    fields = _extract(_block("Batch No.: FB0524"))
    assert fields["batch_number"]["value"] == {"batch": "FB0524"}
    assert fields["use_by"]["status"] == "not_detected"


# ------------------------------------------------------------- net-qty variant

def test_net_quantity_extracted_when_block_is_present() -> None:
    """§9: when the OCR pipeline DOES capture the Net Weight block (another
    render/scan of the same label), it must be extracted — from the anchor's
    neighborhood, never from nutrition numbers."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    blocks = [OCRBlockIn(**b) for b in data["blocks"]]
    blocks.append(
        OCRBlockIn(
            id="block_net", text="Net Weight:", confidence=91.0, page_number=1,
            bbox={"x": 120, "y": 690, "width": 160, "height": 22},
        )
    )
    blocks.append(
        OCRBlockIn(
            id="block_net_val", text="52 g", confidence=93.0, page_number=1,
            bbox={"x": 120, "y": 714, "width": 90, "height": 24},
        )
    )
    page = OCRPageIn(
        page_number=1, width=data["page"]["width"], height=data["page"]["height"],
        full_text=data["page"]["full_text"], blocks=blocks,
    )
    out = {f.field_name: f.model_dump(exclude_none=False) for f in DeterministicFieldExtractor().extract_fields([page])}
    assert out["net_quantity"]["status"] == "detected"
    assert out["net_quantity"]["value"] == {"value": 52.0, "unit": "g"}
    assert {e["ocr_block_id"] for e in out["net_quantity"]["evidence"]} == {"block_net", "block_net_val"}
    # The rest of the extraction is unaffected.
    assert out["batch_number"]["value"] == {"batch": "FB0524"}
