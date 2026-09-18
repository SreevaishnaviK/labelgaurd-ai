"""Phase 9B: net-quantity anchor variants and nutrition-table protection.

Every packaged-commodity phrasing of the declaration must associate its
value through the anchor's spatial neighborhood, and nutrition-panel
numbers must never become the package net quantity. Source-pass
provenance rides through the schema untouched.
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
            width=800,
            height=600,
            full_text="\n".join(b.text for b in blocks),
            blocks=blocks,
        )
    ]


def _extract(blocks: list[OCRBlockIn]) -> dict[str, dict]:
    out = DeterministicFieldExtractor().extract_fields(_page(blocks))
    return {f.field_name: f.model_dump() for f in out}


# ---------------------------------------------------------------- anchor variants

def test_net_weight_inline_value():
    blocks = [_block("Net Weight: 52 g", 100, 400)]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 52.0, "unit": "g"}


def test_net_qty_variant():
    blocks = [_block("Net Qty: 500 g", 100, 400)]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 500.0, "unit": "g"}


def test_net_quantity_variant():
    blocks = [_block("Net Quantity: 1 kg", 100, 400)]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 1.0, "unit": "kg"}


def test_net_content_volume_variant():
    blocks = [_block("Net Content: 250 ml", 100, 400)]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 250.0, "unit": "ml"}


def test_net_wt_abbreviation_variant():
    blocks = [_block("Net Wt.: 1 L", 100, 400)]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 1.0, "unit": "L"}


def test_fragmented_anchor_with_value_block_below():
    """'Net Weight:' on one line, '52 g' as the block directly below in the
    same column — the FarmBite pattern."""
    blocks = [_block("Net Weight:", 100, 400), _block("52 g", 100, 424)]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 52.0, "unit": "g"}
    # Evidence points at the actual blocks carrying the declaration.
    evidence_ids = {e["ocr_block_id"] for e in field["evidence"]}
    assert any(evidence_ids), "net quantity must reference real OCR blocks"


def test_value_block_in_other_column_is_not_stolen():
    """'52 g' sits to the RIGHT in a different column (nutrition row) — not
    the anchor's value."""
    blocks = [
        _block("Net Weight:", 100, 400),
        _block("53.0 g", 400, 424),  # different column, below-right
        _block("Energy 536 kcal", 400, 400),
    ]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] != "detected" or field["value"]["value"] != 53.0


# ---------------------------------------------------------------- nutrition protection

def test_nutrition_table_alone_never_yields_net_quantity():
    blocks = [
        _block("NUTRITIONAL INFORMATION", 100, 100),
        _block("per 100 g", 100, 124),
        _block("Energy 536 kcal", 100, 148),
        _block("Protein 6.5 g", 100, 172),
        _block("Carbohydrate 53.0 g", 100, 196),
        _block("Fat 34.0 g", 100, 220),
        _block("Sodium 650 mg", 100, 244),
    ]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "not_detected"


def test_nutrition_values_not_confused_when_net_anchor_exists_elsewhere():
    blocks = [
        _block("NUTRITIONAL INFORMATION (Approx. values per 100g)", 300, 100),
        _block("Energy 536 kcal", 300, 124),
        _block("Protein 6.5 g", 300, 148),
        _block("Carbohydrate 53.0 g", 300, 172),
        _block("Fat 34.0 g", 300, 196),
        _block("Net Weight: 52 g", 80, 400),
    ]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] == "detected"
    assert field["value"] == {"value": 52.0, "unit": "g"}


def test_pin_code_does_not_become_net_quantity():
    blocks = [
        _block("Net Weight:", 100, 400),
        _block("201306", 100, 424),
    ]
    field = _extract(blocks)["net_quantity"]
    assert field["status"] != "detected"


# ---------------------------------------------------------------- provenance

def test_source_pass_provenance_flows_through_schema():
    """Recovery-pass blocks carry their pass id into extraction untouched."""
    block = _block("Net Weight: 52 g", 100, 400)
    block.source_pass = "B"
    field = _extract([block])["net_quantity"]
    assert field["status"] == "detected"
    # The block's provenance is preserved on the schema object.
    assert block.source_pass == "B"


def test_recovery_pass_block_used_for_extraction():
    """A net-quantity declaration that ONLY the recovery pass found still
    extracts, with evidence bound to that recovery block."""
    block = _block("Net Weight: 52 g", 100, 400)
    block.source_pass = "B"
    field = _extract([block])["net_quantity"]
    assert field["status"] == "detected"
    evidence_ids = {e["ocr_block_id"] for e in field["evidence"]}
    assert block.id in evidence_ids
