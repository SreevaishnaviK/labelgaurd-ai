"""Parse raw OCR words into structured line blocks and full text.

Phase 9A: lines are reconstructed GEOMETRICALLY from word boxes. The engine's
line/block numbers are deliberately ignored — on multi-column layouts
Tesseract's numbering interleaves sub-columns and over-merges table rows, so
trusting it merged the FarmBite manufacturer address into the declaration
line and six nutrition rows into one "line". Geometry is deterministic and
engine-independent.

Grouping (per page), two passes:
1. A word joins a line when its vertical overlap with the line's seed band is
   at least half the smaller height AND the two-sided horizontal gap to the
   line's span is at most ~0.9 of the taller participating height (or the
   word lies fully inside the span). Among fitting lines the smallest gap
   wins. Unplaceable words seed a new line — which can split a visual line
   when words arrive out of x-order.
2. Fragment merge (iterated to stability): two line fragments whose seed
   bands overlap by the same vertical test and whose spans nearly touch
   (gap ≤ 1.5× the taller height) belong to one visual line and are joined.

Words in a line are ordered left-to-right; lines top-to-bottom (then left).
Block bboxes are the exact union of member word boxes. Nothing is
fabricated: blocks exist only where the engine returned words with valid
confidence.
"""
from app.ocr.engine import RawOCRResult, RawWord
from app.schemas.vision import OCRBlock

# Vertical: required overlap as a fraction of the smaller participating height.
_Y_OVERLAP_RATIO = 0.45
# Horizontal: max gap (as a fraction of the taller participating height) that
# still merges two words into one visual line.
_GAP_RATIO = 0.9
# Fragment merge: relaxed horizontal tolerance — fragments already share a
# vertical band, so a slightly wider gap is safe.
_MERGE_GAP_RATIO = 1.5
# Height comparability: two bands may join via the relaxed-gap tier only when
# the smaller height is at least half the taller. Fragments of one visual line
# share font size (ratio ≈ 1), so this only rejects noise-scaled fragments —
# e.g. a 77px-tall barcode smudge fusing with 20px package text.
_HEIGHT_RATIO = 0.5


class _Line:
    """Mutable accumulator for one visual text line."""

    __slots__ = ("seed_y0", "seed_y1", "x0", "x1", "words")

    def __init__(self, word: RawWord) -> None:
        self.seed_y0 = word.y
        self.seed_y1 = word.y + word.height
        self.x0 = word.x
        self.x1 = word.x + word.width
        self.words = [word]

    def vertical_fit(self, y0: int, y1: int) -> bool:
        overlap = min(self.seed_y1, y1) - max(self.seed_y0, y0)
        return overlap >= _Y_OVERLAP_RATIO * min(self.seed_y1 - self.seed_y0, y1 - y0)

    def gap_to(self, x0: int, x1: int) -> int | None:
        """Two-sided horizontal gap to this line's span; None if disjoint x."""
        if x0 >= self.x0 and x1 <= self.x1:
            return 0  # fully inside
        if x1 < self.x0:
            return self.x0 - x1
        if x0 > self.x1:
            return x0 - self.x1
        return 0  # overlapping spans

    def absorb(self, words: list[RawWord]) -> None:
        self.words.extend(words)
        self.x0 = min(self.x0, min(w.x for w in words))
        self.x1 = max(self.x1, max(w.x + w.width for w in words))

    def finish(self) -> None:
        self.words.sort(key=lambda w: w.x)


def _fits(line: _Line, y0: int, y1: int, x0: int, x1: int, gap_ratio: float) -> int | None:
    """Gap to `line` if the band (y0..y1) and span (x0..x1) fit, else None.

    Two tiers: a tight gap (≤ _GAP_RATIO × the SMALLER height) always merges
    — same-line words share font size, and this keeps a normal-height word
    from jumping across a tall noise glyph. A wider gap (up to `gap_ratio` ×
    the taller height) merges only when the two band heights are comparable,
    so an oversized fragment can never bridge unrelated rows.
    """
    if not line.vertical_fit(y0, y1):
        return None
    gap = line.gap_to(x0, x1)
    h_a, h_b = y1 - y0, line.seed_y1 - line.seed_y0
    if gap <= _GAP_RATIO * min(h_a, h_b):
        return gap
    taller = max(h_a, h_b)
    if gap <= gap_ratio * taller and min(h_a, h_b) >= _HEIGHT_RATIO * taller:
        return gap
    return None


def _group_lines(words: list[RawWord]) -> list[_Line]:
    lines: list[_Line] = []
    for word in sorted(words, key=lambda w: (w.y, w.x)):
        x1 = word.x + word.width
        y1 = word.y + word.height
        candidates = [
            (gap, line)
            for line in lines
            if (gap := _fits(line, word.y, y1, word.x, x1, _GAP_RATIO)) is not None
        ]
        if candidates:
            min(candidates, key=lambda c: c[0])[1].absorb([word])
        else:
            lines.append(_Line(word))
    return lines


def _merge_fragments(lines: list[_Line]) -> list[_Line]:
    """Join split fragments of the same visual line until stable."""
    for _ in range(3):  # deterministic cap; converges in 1-2 passes in practice
        merged_any = False
        for i, a in enumerate(lines):
            if not a.words:
                continue
            for j in range(i + 1, len(lines)):
                b = lines[j]
                if not b.words:
                    continue
                gap = _fits(a, b.seed_y0, b.seed_y1, b.x0, b.x1, _MERGE_GAP_RATIO)
                if gap is not None:
                    a.absorb(b.words)
                    a.x1 = max(a.x1, b.x1)
                    b.words = []
                    merged_any = True
        if not merged_any:
            break
    return [line for line in lines if line.words]


def parse_blocks(result: RawOCRResult, page_number: int) -> list[OCRBlock]:
    """Build geometrically-ordered OCRBlock list from raw engine words for one page."""
    words = [w for w in result.words if w.text.strip()]
    lines = _merge_fragments(_group_lines(words))
    for line in lines:
        line.finish()
    lines.sort(key=lambda ln: (min(w.y for w in ln.words), ln.x0))

    blocks: list[OCRBlock] = []
    for index, line in enumerate(lines, start=1):
        text = " ".join(word.text for word in line.words).strip()
        if not text:
            continue
        confidence = sum(word.confidence for word in line.words) / len(line.words)
        x0 = min(word.x for word in line.words)
        x1 = max(word.x + word.width for word in line.words)
        y0 = min(word.y for word in line.words)
        y1 = max(word.y + word.height for word in line.words)
        blocks.append(
            OCRBlock(
                id=f"block_{index:03d}",
                text=text,
                confidence=round(confidence, 1),
                bbox={"x": x0, "y": y0, "width": max(1, x1 - x0), "height": max(1, y1 - y0)},
                line_number=index,
                block_number=index,
                page_number=page_number,
            )
        )
    return blocks


def join_full_text(blocks: list[OCRBlock]) -> str:
    """Join block texts in reading order, blank line between blocks."""
    return "\n\n".join(block.text for block in blocks if block.text.strip())
