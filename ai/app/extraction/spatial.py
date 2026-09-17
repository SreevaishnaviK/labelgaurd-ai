"""Spatial analysis of OCR blocks: reading order, lines, sections.

Phase 9A. OCR blocks arrive as (text, bbox, confidence) with NO guaranteed
reading order, and engine line numbers are unreliable on multi-column labels
(they interleaved the FarmBite manufacturer declaration with its address).
This module rebuilds geometry deterministically from block bboxes only:

1. ``group_lines``       — blocks sharing a vertical band become one visual
   line; word order inside a line is left-to-right.
2. ``reading_order``     — lines top-to-bottom, left-to-right inside a band.
3. ``find_anchor``       — regex anchors located WITH their visual line.
4. ``neighborhood``      — the spatial candidate set for an anchor: same line
   (after the anchor), lines BELOW overlapping it horizontally, lines RIGHT
   sharing its band, and optionally lines ABOVE. Never the whole document.

Pure functions over ``OCRBlockIn``; nothing here decides legality or
normalizes values. This replaces the old "search all blocks in reading order"
pattern that made fields bleed across sections.
"""
import re

from app.schemas.extraction import OCRBlockIn

# A block joins a visual line when the vertical overlap with the line's seed
# band is at least this fraction of the smaller height.
_Y_OVERLAP_RATIO = 0.45


class VisualLine:
    """One reconstructed visual text line: ordered blocks + union bbox."""

    __slots__ = ("blocks", "y0", "y1")

    def __init__(self, first: OCRBlockIn) -> None:
        bbox = first.bbox or {}
        self.y0 = bbox.get("y", 0)
        self.y1 = self.y0 + bbox.get("height", 0)
        self.blocks = [first]

    def fits(self, block: OCRBlockIn) -> bool:
        bbox = block.bbox or {}
        y0 = bbox.get("y", 0)
        y1 = y0 + bbox.get("height", 0)
        overlap = min(self.y1, y1) - max(self.y0, y0)
        return overlap >= _Y_OVERLAP_RATIO * min(self.y1 - self.y0, y1 - y0)

    def absorb(self, block: OCRBlockIn) -> None:
        self.blocks.append(block)
        bbox = block.bbox or {}
        self.y0 = min(self.y0, bbox.get("y", 0))
        self.y1 = max(self.y1, bbox.get("y", 0) + bbox.get("height", 0))
        self.blocks.sort(key=_left_edge)

    @property
    def text(self) -> str:
        return " ".join(b.text.strip() for b in self.blocks if b.text.strip())

    @property
    def x0(self) -> int:
        return min((_left_edge(b) for b in self.blocks), default=0)

    @property
    def x1(self) -> int:
        return max((_right_edge(b) for b in self.blocks), default=0)

    def overlaps_horizontally(self, x0: int, x1: int) -> bool:
        return min(self.x1, x1) - max(self.x0, x0) > 0


def _left_edge(block: OCRBlockIn) -> int:
    return (block.bbox or {}).get("x", 0)


def _right_edge(block: OCRBlockIn) -> int:
    bbox = block.bbox or {}
    return bbox.get("x", 0) + bbox.get("width", 0)


def group_lines(blocks: list[OCRBlockIn]) -> list[VisualLine]:
    """Reconstruct visual lines from block geometry, top-to-bottom."""
    lines: list[VisualLine] = []
    for block in sorted(blocks, key=lambda b: ((b.bbox or {}).get("y", 0), _left_edge(b))):
        for line in reversed(lines):
            if line.fits(block):
                line.absorb(block)
                break
        else:
            lines.append(VisualLine(block))
    lines.sort(key=lambda ln: (ln.y0, ln.x0))
    return lines


def reading_order(blocks: list[OCRBlockIn]) -> list[VisualLine]:
    """Visual lines in reading order (alias — grouping is already ordered)."""
    return group_lines(blocks)


def find_anchor(lines: list[VisualLine], pattern: re.Pattern) -> list[tuple[VisualLine, re.Match]]:
    """All lines whose joined text matches the anchor pattern."""
    hits = []
    for line in lines:
        match = pattern.search(line.text)
        if match:
            hits.append((line, match))
    return hits


def neighborhood(
    lines: list[VisualLine],
    anchor_line: VisualLine,
    *,
    below: int = 4,
    above: int = 0,
    right: bool = True,
) -> list[VisualLine]:
    """Spatial candidate set for an anchor — never the whole document.

    Included, in order: the anchor line itself (text after the match is the
    caller's concern), up to `below` subsequent lines that chain to it — each
    must be vertically contiguous with the previous included line (overlap or
    a small gap, not a far jump) and horizontally overlap the anchor's column
    (or the previous line's span). Same-band lines to the right when `right`
    (side-by-side columns), and up to `above` preceding lines when explicitly
    requested (e.g. a value printed ABOVE its label). Distant sections in
    reading order are excluded even when OCR returned them consecutively.
    """
    start = lines.index(anchor_line)
    selected: list[VisualLine] = [anchor_line]

    def _band_overlaps(a: VisualLine, b: VisualLine) -> bool:
        return min(a.y1, b.y1) - max(a.y0, b.y0) > 0

    below_count = 0
    prev = anchor_line
    for line in lines[start + 1 :]:
        if below_count >= below:
            break
        height = max(prev.y1 - prev.y0, line.y1 - line.y0, 1)
        contiguous = line.y0 - prev.y1 <= 0.6 * height  # overlap or small gap
        column = line.overlaps_horizontally(
            anchor_line.x0, anchor_line.x1
        ) or line.overlaps_horizontally(prev.x0, prev.x1)
        if contiguous and column:
            selected.append(line)
            below_count += 1
            prev = line
        elif contiguous:
            continue  # side noise within the band: skip, keep chaining
        else:
            break  # vertical gap: the section ends here

    if right:
        for line in lines[:start]:
            if _band_overlaps(anchor_line, line) and line.x0 >= anchor_line.x1:
                selected.append(line)

    for line in reversed(lines[:start]):
        if above == 0:
            break
        if _band_overlaps(anchor_line, line) and line.overlaps_horizontally(
            anchor_line.x0, anchor_line.x1
        ):
            selected.insert(1, line)
            above -= 1

    return selected
