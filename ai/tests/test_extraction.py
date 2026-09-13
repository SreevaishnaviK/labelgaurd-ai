"""Deterministic extraction tests: per-field behavior, ambiguity, evidence.

All inputs are synthetic OCR blocks; assertions verify real extraction logic
including normalization, evidence linking, and confidence propagation.
"""
import pytest

from app.extraction.deterministic import DeterministicFieldExtractor
from app.schemas.extraction import OCRBlockIn, OCRPageIn


def _block(text: str, block_id: str = "block_001", confidence: float = 96.0, x: int = 100, y: int = 100, width: int = 400, height: int = 40, page: int = 1) -> OCRBlockIn:
    return OCRBlockIn(
        id=block_id,
        text=text,
        confidence=confidence,
        page_number=page,
        bbox={"x": x, "y": y, "width": width, "height": height},
    )


def _page(*blocks: OCRBlockIn) -> list[OCRPageIn]:
    return [OCRPageIn(page_number=1, width=1920, height=1080, full_text="\n".join(b.text for b in blocks), blocks=list(blocks))]


def _extract(*blocks: OCRBlockIn) -> dict[str, dict]:
    fields = DeterministicFieldExtractor().extract_fields(_page(*blocks))
    return {f.field_name: f.model_dump(exclude_none=False) for f in fields}


# ------------------------------------------------------------- MRP (§ patterns)

@pytest.mark.parametrize(
    "text",
    [
        "MRP ₹68",
        "MRP Rs. 68",
        "MRP Rs 68",
        "M.R.P. ₹68",
        "Maximum Retail Price ₹68",
        "Maximum Retail Price: Rs. 68",
    ],
)
def test_mrp_all_indicator_patterns(text: str) -> None:
    fields = _extract(_block(text))
    assert fields["mrp"]["status"] == "detected"
    assert fields["mrp"]["value"] == {"amount": 68.0, "currency": "INR"}
    assert fields["mrp"]["raw_text"]


def test_mrp_decimal_and_comma() -> None:
    fields = _extract(_block("MRP ₹ 1,299.50"))
    assert fields["mrp"]["value"] == {"amount": 1299.5, "currency": "INR"}


def test_mrp_not_inferred_without_indicator() -> None:
    fields = _extract(_block("Price ₹68"), _block("₹68 only"))
    assert fields["mrp"]["status"] == "not_detected"


# ------------------------------------------------------------- net quantity

@pytest.mark.parametrize(
    "text, expected",
    [
        ("Net Qty: 1 kg", {"value": 1, "unit": "kg"}),
        ("Net Quantity 500 g", {"value": 500, "unit": "g"}),
        ("Net Wt. 500 g", {"value": 500, "unit": "g"}),
        ("Net Weight: 500g", {"value": 500, "unit": "g"}),
        ("Contents: 1 L", {"value": 1, "unit": "L"}),
        ("Net Qty: 1500 ml", {"value": 1.5, "unit": "L"}),  # canonical unit chosen
        ("Net Qty: 2 kg", {"value": 2, "unit": "kg"}),
    ],
)
def test_net_quantity_units(text: str, expected: dict) -> None:
    fields = _extract(_block(text))
    assert fields["net_quantity"]["status"] == "detected"
    assert fields["net_quantity"]["value"] == expected


def test_net_quantity_not_confused_with_other_numbers() -> None:
    fields = _extract(_block("Batch 250 g sample code"), _block("Call 1800 123 456"))
    assert fields["net_quantity"]["status"] == "not_detected"


# ------------------------------------------------------------- product name

def test_product_name_prefers_prominent_top_block() -> None:
    fields = _extract(
        _block("PREMIUM WHEAT FLOUR", "block_001", y=40, width=800, height=90),
        _block("Net Qty: 1 kg", "block_002", y=300),
        _block("MRP ₹68.00", "block_003", y=400),
        _block("Manufactured by ABC Foods Pvt Ltd", "block_004", y=500),
    )
    assert fields["product_name"]["status"] == "detected"
    assert fields["product_name"]["value"]["name"] == "PREMIUM WHEAT FLOUR"
    assert fields["product_name"]["evidence"][0]["ocr_block_id"] == "block_001"


def test_product_name_not_a_reserved_field() -> None:
    fields = _extract(_block("Batch No WF2408", "block_001", y=40, width=800, height=90))
    assert fields["product_name"]["status"] == "not_detected"


def test_product_name_not_first_block_when_reserved() -> None:
    fields = _extract(
        _block("MRP ₹68.00", "block_001", y=40, width=800, height=90),
        _block("Golden Harvest Atta", "block_002", y=200, width=600, height=80),
    )
    assert fields["product_name"]["value"]["name"] == "Golden Harvest Atta"


# ------------------------------------------------------------- roles + addresses

def test_manufacturer_basic() -> None:
    fields = _extract(_block("Manufactured by ABC Foods Pvt Ltd"))
    assert fields["manufacturer"]["value"] == {"name": "ABC Foods Pvt Ltd"}


def test_manufactured_and_marketed_by() -> None:
    fields = _extract(_block("Manufactured & Marketed by Sharma Industries"))
    assert fields["manufacturer"]["value"]["name"] == "Sharma Industries"


def test_packer_and_importer() -> None:
    fields = _extract(
        _block("Packed by FreshPack Ltd"),
        _block("Imported by Global Imports Inc"),
    )
    assert fields["packer"]["value"]["name"] == "FreshPack Ltd"
    assert fields["importer"]["value"]["name"] == "Global Imports Inc"


def test_multi_block_address_evidence() -> None:
    fields = _extract(
        _block("Manufactured by ABC Foods Pvt Ltd", "block_001", y=500, height=40),
        _block("Plot 12, Industrial Estate", "block_002", y=545, height=40),
        _block("Vijayawada, Andhra Pradesh", "block_003", y=590, height=40),
    )
    assert fields["manufacturer"]["value"]["name"].startswith("ABC Foods")
    evidence_ids = [e["ocr_block_id"] for e in fields["manufacturer"]["evidence"]]
    assert evidence_ids == ["block_001", "block_002", "block_003"]


# ------------------------------------------------------------- dates

@pytest.mark.parametrize(
    "text, field_name, date",
    [
        ("MFD 12/08/2025", "manufacturing_date", "12/08/2025"),
        ("MFG 12-08-25", "manufacturing_date", "12-08-25"),
        ("Manufacturing Date: 12.08.2025", "manufacturing_date", "12.08.2025"),
        ("PKD 10/2025", "packing_date", "10/2025"),
        ("Packing Date 10-2025", "packing_date", "10-2025"),
        ("Best Before 09/2026", "best_before", "09/2026"),
        ("Use By 09-2026", "use_by", "09-2026"),
        ("EXP 08/2026", "expiry_date", "08/2026"),
        ("Expiry 08/2026", "expiry_date", "08/2026"),
    ],
)
def test_date_formats(text: str, field_name: str, date: str) -> None:
    fields = _extract(_block(text))
    assert fields[field_name]["status"] == "detected"
    assert fields[field_name]["value"] == {"date": date}


# ------------------------------------------------------------- batch / lot

def test_batch_number() -> None:
    fields = _extract(_block("Batch No: WF240812"))
    assert fields["batch_number"]["value"] == {"batch": "WF240812"}


def test_lot_number() -> None:
    fields = _extract(_block("Lot No. L-99231"))
    assert fields["lot_number"]["value"] == {"batch": "L-99231"}


def test_batch_not_confused_with_random_numbers() -> None:
    fields = _extract(_block("Call 1800 123 456 for help"))
    assert fields["batch_number"]["status"] == "not_detected"


# ------------------------------------------------------------- contacts

def test_consumer_care_phone() -> None:
    fields = _extract(_block("Consumer Care: 1800-123-4567"))
    assert fields["customer_care_phone"]["value"] == {"phone": "18001234567"}
    assert fields["consumer_care"]["status"] == "detected"


def test_phone_with_indicator_on_same_line() -> None:
    fields = _extract(_block("Customer Care 1800 123 4567"))
    assert fields["customer_care_phone"]["value"] == {"phone": "18001234567"}


def test_email_extracted() -> None:
    fields = _extract(_block("Customer Care: care@abcfoods.com"))
    assert fields["customer_care_email"]["value"] == {"email": "care@abcfoods.com"}


def test_website_extracted() -> None:
    fields = _extract(_block("www.abcfoods.com"))
    assert fields["website"]["value"] == {"url": "https://www.abcfoods.com"}
    fields = _extract(_block("Visit https://example.in/products"))
    assert fields["website"]["value"] == {"url": "https://example.in/products"}


def test_random_phone_without_indicator_not_consumer_care() -> None:
    fields = _extract(_block("Order number 9876543210 confirmed"))
    assert fields["customer_care_phone"]["status"] == "not_detected"


# ------------------------------------------------------------- origin / ingredients / veg

def test_country_of_origin_variants() -> None:
    for text, expected in [
        ("Country of Origin: India", "India"),
        ("Made in India", "India"),
        ("Product of India", "India"),
    ]:
        fields = _extract(_block(text))
        assert fields["country_of_origin"]["value"] == {"country": expected}


def test_ingredients_multiline() -> None:
    fields = _extract(
        _block("Ingredients:", "block_001", y=100, height=30),
        _block("Wheat flour, sugar, salt", "block_002", y=135, height=40),
    )
    assert fields["ingredients"]["status"] == "detected"
    assert "Wheat flour" in fields["ingredients"]["value"]["ingredients"]
    assert {e["ocr_block_id"] for e in fields["ingredients"]["evidence"]} == {"block_001", "block_002"}


def test_vegetarian_and_nonvegetarian() -> None:
    fields = _extract(_block("VEGETARIAN"))
    assert fields["vegetarian_non_vegetarian"]["value"] == {"declaration": "vegetarian"}
    fields = _extract(_block("NON-VEG"))
    assert fields["vegetarian_non_vegetarian"]["value"] == {"declaration": "non_vegetarian"}


# ------------------------------------------------------------- ambiguity / absence

def test_ambiguous_mrp_surfaces_candidates() -> None:
    fields = _extract(_block("MRP ₹68", "block_001"), _block("M.R.P. ₹72", "block_002"))
    assert fields["mrp"]["status"] == "ambiguous"
    assert fields["mrp"]["value"] is None
    values = [c["value"]["amount"] for c in fields["mrp"]["candidates"]]
    assert values == [68.0, 72.0]


def test_not_detected_fields_are_complete() -> None:
    """A lone descriptive block is a plausible product name; all other 22
    fields must report not_detected with null values."""
    fields = _extract(_block("Delicious tasty snack"))
    detected = [name for name, f in fields.items() if f["status"] == "detected"]
    assert detected == ["product_name"]
    not_detected = [name for name, f in fields.items() if f["status"] == "not_detected"]
    assert len(not_detected) == 22
    for name in not_detected:
        assert fields[name]["value"] is None


# ------------------------------------------------------------- evidence + confidence

def test_evidence_links_block_ids_and_page() -> None:
    fields = _extract(_block("MRP ₹68.00", "block_023", confidence=96.4, page=2))
    evidence = fields["mrp"]["evidence"]
    assert evidence == [{"ocr_block_id": "block_023", "page_number": 2}]


def test_ocr_confidence_propagates_and_averages() -> None:
    fields = _extract(
        _block("Manufactured by", "block_001", confidence=90.0),
        _block("ABC Foods Pvt Ltd", "block_002", confidence=100.0),
    )
    assert fields["manufacturer"]["ocr_confidence"] == 95.0


def test_extraction_confidence_generated() -> None:
    fields = _extract(_block("MRP ₹68.00", confidence=96.4))
    assert fields["mrp"]["extraction_confidence"] is not None
    assert 0 <= fields["mrp"]["extraction_confidence"] <= 100


def test_multi_block_evidence_includes_all_supporting_blocks() -> None:
    fields = _extract(
        _block("Best Before", "block_001", y=700, height=30),
        _block("09/2026", "block_002", y=735, height=40),
    )
    # Date written across two blocks: indicator block + value block.
    evidence = fields["best_before"]["evidence"]
    assert evidence[0]["ocr_block_id"] == "block_001"


# ------------------------------------------------------------- no compliance leakage

def test_no_compliance_vocabulary_in_output() -> None:
    fields = _extract(
        _block("PREMIUM WHEAT FLOUR", "block_001"),
        _block("MRP ₹68.00", "block_002"),
    )
    serialized = str(fields)
    for banned in ("compliant", "non-compliant", "violation", "compliance_score", "legal"):
        assert banned not in serialized.lower()
