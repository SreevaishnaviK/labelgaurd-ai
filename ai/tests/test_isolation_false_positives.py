"""Phase 9C: cross-field false-positive matrix (§26).

Each test proves one contamination path stays closed: a candidate that
matches a pattern but lacks its anchor, section, or semantic validity is
NOT extracted. ``not_detected`` is the expected outcome for every
wrong-field candidate — a wrong value is worse than a missing one.
"""
from app.extraction.deterministic import DeterministicFieldExtractor
from app.schemas.extraction import OCRBlockIn, OCRPageIn

_SEQ = iter(range(1, 10_000))


def _block(text: str, x: int, y: int, width: int | None = None, confidence: float = 92.0) -> OCRBlockIn:
    return OCRBlockIn(
        id=f"block_{next(_SEQ):03d}",
        text=text,
        confidence=confidence,
        page_number=1,
        bbox={"x": x, "y": y, "width": width if width is not None else 12 * len(text), "height": 20},
        line_number=y // 20 + 1,
        block_number=x // 100 + 1,
    )


def _page(blocks: list[OCRBlockIn]) -> list[OCRPageIn]:
    return [
        OCRPageIn(
            page_number=1,
            width=900,
            height=600,
            full_text="\n".join(b.text for b in blocks),
            blocks=blocks,
        )
    ]


def _extract(blocks: list[OCRBlockIn]) -> dict[str, dict]:
    out = DeterministicFieldExtractor().extract_fields(_page(blocks))
    return {f.field_name: f.model_dump() for f in out}


def _status(fields: dict[str, dict], name: str) -> str:
    """Status of a field; absent entries mean not_detected."""
    return fields.get(name, {}).get("status", "not_detected")


# --- product name: declarations, banners and sections are not titles (§3/§9) ---


def test_allergen_statement_is_not_product_name():
    fields = _extract([_block("Contains milk. May contain traces of nuts.", 100, 80)])
    assert _status(fields, "product_name") == "not_detected"


def test_mrp_number_is_not_batch_or_product_name():
    fields = _extract(
        [
            _block("MRP ₹ 45.00", 100, 400),
            _block("45.00", 300, 420),
        ]
    )
    assert fields["mrp"]["status"] == "detected"
    assert fields["mrp"]["value"]["amount"] == 45.0
    assert _status(fields, "batch_number") == "not_detected"
    assert _status(fields, "product_name") == "not_detected"


def test_random_alphanumeric_without_batch_anchor_is_not_batch():
    """FB0726 with NO Batch/Lot anchor anywhere must not become the batch."""
    fields = _extract(
        [
            _block("FarmBite Potato Chips", 100, 60),
            _block("FB0726", 100, 300),
        ]
    )
    assert _status(fields, "batch_number") == "not_detected"


def test_fssai_licence_number_is_not_batch():
    fields = _extract(
        [
            _block("Lic. No. 10012021000123", 100, 60),
            _block("10012021000123", 100, 300),
        ]
    )
    assert _status(fields, "batch_number") == "not_detected"


def test_mrp_without_anchor_is_not_detected():
    fields = _extract([_block("45.00", 100, 400)])
    assert _status(fields, "mrp") == "not_detected"


# --- phone: identifiers are not consumer-care numbers (§14) ---


def test_barcode_digits_are_not_phone():
    fields = _extract(
        [
            _block("8901234567890", 100, 60),
            _block("Net Qty: 500 g", 100, 200),
        ]
    )
    assert _status(fields, "customer_care_phone") == "not_detected"


def test_phone_requires_consumer_care_context():
    fields = _extract([_block("1800 123 4567", 100, 60)])
    assert _status(fields, "customer_care_phone") == "not_detected"


# --- ingredients: nutrition vocabulary is rejected (§8) ---


def test_nutrition_table_is_not_ingredients():
    fields = _extract(
        [
            _block("NUTRITIONAL INFORMATION", 100, 60),
            _block("Energy 545 kcal", 100, 90),
            _block("Protein 6.5 g", 100, 120),
        ]
    )
    assert _status(fields, "ingredients") == "not_detected"


# --- dates: one declaration per field, no copying (§11/§12) ---


def test_use_by_does_not_populate_manufacturing_date():
    fields = _extract(
        [
            _block("Use By: 15 NOV 2024", 100, 300),
            _block("Best Before: 09 JAN 2027", 100, 330),
        ]
    )
    assert fields["use_by"]["value"]["date"] == "15 NOV 2024"
    assert fields["best_before"]["value"]["date"] == "09 JAN 2027"
    assert _status(fields, "manufacturing_date") == "not_detected"
    assert _status(fields, "packing_date") == "not_detected"


def test_mfg_date_does_not_fill_packing_date():
    fields = _extract([_block("Mfg Date: 10 JUL 2026", 100, 300)])
    assert fields["manufacturing_date"]["value"]["date"] == "10 JUL 2026"
    assert _status(fields, "packing_date") == "not_detected"


# --- website/email: only visible, evidenced declarations (§15/§16) ---


def test_bare_domain_word_is_not_website():
    fields = _extract([_block("visit farmbite dot in today", 100, 60)])
    assert _status(fields, "website") == "not_detected"


def test_email_without_context_is_not_customer_care():
    fields = _extract([_block("care@abc.com", 100, 60)])
    assert _status(fields, "customer_care_email") == "not_detected"
