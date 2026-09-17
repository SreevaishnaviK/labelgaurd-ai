"""Phase 9A regression: the block parser on the REAL FarmBite OCR output.

The persisted corruption (manufacturer fused with its address, nutrition rows
merged across lines) came from trusting Tesseract line_num on a multi-column
label. These tests pin the geometric reconstruction on the actual word data.
"""
import json
from pathlib import Path

from app.ocr.engine import RawOCRResult, RawWord
from app.ocr.parser import parse_blocks, join_full_text

FIXTURE = Path(__file__).parent / "fixtures" / "farmbite_words.json"


def _result() -> RawOCRResult:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    words = [RawWord(**w) for w in data["words"]]
    return RawOCRResult(words=words, width=data["width"], height=data["height"])


def test_manufacturer_declaration_reconstructed_cleanly() -> None:
    blocks = parse_blocks(_result(), page_number=1)
    texts = [b.text for b in blocks]
    assert "MANUFACTURED & PACKED BY:" in texts
    assert "FarmBite Foods Pvt. Ltd." in texts
    assert "Plot No. 42, Food Park, Sector 8," in texts
    assert "Greater Noida, Uttar Pradesh - 201306; India." in texts
    # The old bug: declaration + address fused into one block.
    assert not any(
        "MANUFACTURED" in t and "Plot No. 42" in t for t in texts
    ), "manufacturer declaration must not be fused with the address"


def test_nutrition_rows_not_merged_across_lines() -> None:
    blocks = parse_blocks(_result(), page_number=1)
    texts = [b.text for b in blocks]
    energy = next(t for t in texts if t.startswith("Energy"))
    assert "Protein" not in energy, "nutrition rows must stay on their own lines"
    assert any(t == "INGREDIENTS:" for t in texts)


def test_full_text_reading_order_is_spatial() -> None:
    text = join_full_text(parse_blocks(_result(), page_number=1))
    ingredients_at = text.index("INGREDIENTS:")
    potatoes_at = text.index("Potatoes")
    manufactured_at = text.index("MANUFACTURED & PACKED BY:")
    assert potatoes_at < manufactured_at
    assert ingredients_at < potatoes_at
