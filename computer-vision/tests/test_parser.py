"""Parser/confidence tests using synthetic raw OCR words (no Tesseract needed)."""
from app.ocr.confidence import average_confidence
from app.ocr.engine import RawOCRResult, RawWord
from app.ocr.parser import join_full_text, parse_blocks


def _result(words: list[RawWord], width: int = 1000, height: int = 500) -> RawOCRResult:
    return RawOCRResult(words=words, width=width, height=height)


def test_words_in_same_line_merge() -> None:
    words = [
        RawWord("MRP", 95.0, 100, 820, 60, 30, 1, 4),
        RawWord("₹68.00", 97.0, 170, 820, 110, 30, 1, 4),
    ]
    blocks = parse_blocks(_result(words), page_number=1)
    assert len(blocks) == 1
    assert blocks[0].text == "MRP ₹68.00"
    assert blocks[0].bbox.x == 100
    assert blocks[0].bbox.width == 180
    assert blocks[0].confidence == 96.0


def test_reading_order_not_alphabetical() -> None:
    words = [
        RawWord("zebra", 90.0, 100, 100, 60, 30, 1, 1),
        RawWord("apple", 90.0, 100, 200, 60, 30, 2, 1),
    ]
    blocks = parse_blocks(_result(words), page_number=1)
    assert [block.text for block in blocks] == ["zebra", "apple"]


def test_empty_text_not_a_block() -> None:
    words = [RawWord("   ", 90.0, 10, 10, 20, 20, 1, 1)]
    assert parse_blocks(_result(words), page_number=1) == []


def test_block_ids_sequential() -> None:
    words = [
        RawWord("one", 90.0, 10, 10, 20, 20, 1, 1),
        RawWord("two", 90.0, 10, 60, 20, 20, 2, 1),
        RawWord("three", 90.0, 10, 110, 20, 20, 3, 1),
    ]
    blocks = parse_blocks(_result(words), page_number=1)
    assert [block.id for block in blocks] == ["block_001", "block_002", "block_003"]


def test_page_number_preserved() -> None:
    words = [RawWord("text", 90.0, 10, 10, 20, 20, 1, 1)]
    blocks = parse_blocks(_result(words), page_number=3)
    assert blocks[0].page_number == 3


def test_full_text_join() -> None:
    words = [
        RawWord("Premium", 95.0, 100, 100, 120, 30, 1, 1),
        RawWord("MRP", 95.0, 100, 200, 60, 30, 2, 1),
    ]
    blocks = parse_blocks(_result(words), page_number=1)
    assert join_full_text(blocks) == "Premium\n\nMRP"


def test_average_confidence_empty() -> None:
    assert average_confidence([]) == 0.0


def test_average_confidence_rounds() -> None:
    assert average_confidence([90.0, 95.0]) == 92.5
