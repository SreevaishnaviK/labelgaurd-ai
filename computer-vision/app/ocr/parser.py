"""Parse raw OCR words into structured line blocks and full text.

Grouping: words from the same Tesseract block + line merge into one text
block, in reading order (top-to-bottom, left-to-right). The union of word
boxes forms the block bbox. Nothing is fabricated: blocks exist only where
the engine returned words with valid confidence.
"""
from app.ocr.engine import RawOCRResult, RawWord
from app.schemas.vision import OCRBlock


def _group_words(result: RawOCRResult) -> dict[tuple[int, int], list[RawWord]]:
    groups: dict[tuple[int, int], list[RawWord]] = {}
    for word in result.words:
        groups.setdefault((word.block_number, word.line_number), []).append(word)
    # Reading order within a group: left to right.
    for words in groups.values():
        words.sort(key=lambda w: (w.x, w.y))
    return groups


def parse_blocks(result: RawOCRResult, page_number: int) -> list[OCRBlock]:
    """Build ordered OCRBlock list from raw engine words for one page."""
    groups = _group_words(result)
    # Global reading order across lines: by block then top coordinate.
    ordered_keys = sorted(
        groups.keys(),
        key=lambda key: (
            key[0],
            min(word.y for word in groups[key]),
            min(word.x for word in groups[key]),
        ),
    )

    blocks: list[OCRBlock] = []
    for index, key in enumerate(ordered_keys, start=1):
        words = groups[key]
        text = " ".join(word.text for word in words).strip()
        if not text:
            continue
        x = min(word.x for word in words)
        y = min(word.y for word in words)
        right = max(word.x + word.width for word in words)
        bottom = max(word.y + word.height for word in words)
        confidence = sum(word.confidence for word in words) / len(words)
        blocks.append(
            OCRBlock(
                id=f"block_{index:03d}",
                text=text,
                confidence=round(confidence, 1),
                bbox={"x": x, "y": y, "width": max(1, right - x), "height": max(1, bottom - y)},
                line_number=words[0].line_number,
                block_number=words[0].block_number,
                page_number=page_number,
            )
        )
    return blocks


def join_full_text(blocks: list[OCRBlock]) -> str:
    """Join block texts in reading order, blank line between blocks."""
    return "\n\n".join(block.text for block in blocks if block.text.strip())
