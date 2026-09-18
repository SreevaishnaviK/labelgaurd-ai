"""Multi-pass OCR with conservative block-level merging (Phase 9B).

Pass A (the established pipeline) misses some small, low-contrast
declarations — on a real chips label the denoise/threshold stages erased
"Net Weight: 52g" that a contrast-only variant reads at 96% confidence.
Rather than changing pass A's behavior for every image, extra passes run
only when pass A's coverage suggests a missed mandatory declaration, and
their blocks are merged in only where they genuinely add coverage.

Merging rules (§3):
- one merged block per (page, IoU-overlap) neighborhood — no duplicate
  logical fields downstream;
- the higher-confidence detection wins; equal confidence prefers pass A
  (the established pipeline);
- every block records the pass that produced it, so evidence keeps its
  provenance. Pass A output is never altered.
"""
import logging
import re
import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.ocr.engine import BaseOCREngine, RawWord
from app.ocr.parser import parse_blocks
from app.preprocessing.enhance import enhance_contrast

logger = logging.getLogger(__name__)

# Mandatory-declaration anchors whose absence triggers recovery passes.
# Generic packaged-commodity vocabulary — nothing product-specific.
_ANCHOR_RE = re.compile(
    r"\b(?:net\s*(?:weight|wt|qty|quantity|content)|m\.?r\.?p|batch|lot|"
    r"use\s*by|best\s*before|expiry|mfg|manufactur|packer|ingredient|"
    r"customer\s*care|consumer\s*care|country\s*of\s*origin)\b",
    re.IGNORECASE,
)

# The net-quantity declaration is universally mandatory on packaged
# commodities and routinely set in small print — the classic casualty of
# aggressive binarization. Recovery escalates specifically when its anchor
# is missing, even if other declarations were found.
_NET_ANCHOR_RE = re.compile(
    r"\bnet\s*(?:weight|wt|qty|quantity|content)|\bcontents\b", re.IGNORECASE
)

# Pass B: CLAHE-contrast-only variant of the base image (no denoise, no
# threshold, no sharpen) — the stages that erased small low-contrast text.
_PASS_B_CLIP = 2.0
# Recovery passes read unthresholded images, so graphics (leaves, barcodes)
# surface as low-confidence junk. A recovery block only merges when the
# engine itself was confident — weaker reads stay out of the evidence.
_RECOVERY_MIN_CONFIDENCE = 50.0


@dataclass
class MultiPassResult:
    blocks: list
    passes_run: list[str]
    extra_time_ms: int = 0


def _bbox_iou(a: dict, b: dict) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["width"], a["y"] + a["height"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if inter == 0:
        return 0.0
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union


def _blocks_have_anchor(blocks) -> bool:
    return any(_ANCHOR_RE.search(b.text) for b in blocks)


def _blocks_have_net_anchor(blocks) -> bool:
    return any(_NET_ANCHOR_RE.search(b.text) for b in blocks)


def _contrast_pass(clean_gray: np.ndarray) -> np.ndarray:
    """CLAHE-only variant of the CLEAN grayscale — skipping the denoise,
    threshold and sharpen stages is the point: those erased the faint text."""
    clahe = cv2.createCLAHE(clipLimit=_PASS_B_CLIP, tileGridSize=(8, 8))
    return clahe.apply(clean_gray)


def _upscaled(gray: np.ndarray) -> np.ndarray:
    return cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)


def _new_words_from(words: list[RawWord], scale_x: float, scale_y: float, y_offset: int) -> list[RawWord]:
    """Map raw words from a transformed image back to base-page coordinates."""
    out = []
    for w in words:
        out.append(
            RawWord(
                text=w.text,
                confidence=w.confidence,
                x=int(round(w.x / scale_x)),
                y=int(round(w.y / scale_y)) + y_offset,
                width=max(1, int(round(w.width / scale_x))),
                height=max(1, int(round(w.height / scale_y))),
                line_number=w.line_number,
                block_number=w.block_number,
                par_num=w.par_num,
            )
        )
    return out


def _center_in(box: dict, other: dict) -> bool:
    """True when box's center lies inside other — same-detection test that
    survives cross-scale bbox shifts (a 2x pass remaps slightly differently
    but keeps the same physical center)."""
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    return (
        other["x"] <= cx <= other["x"] + other["width"]
        and other["y"] <= cy <= other["y"] + other["height"]
    )


def _merge_blocks(base_blocks: list, extra_blocks: list, iou_threshold: float = 0.2) -> list:
    """Merge extra blocks into base ones: higher confidence wins, pass A ties.

    Duplicates are detected two ways: IoU ≥ threshold, or either box's center
    falling inside the other (cross-scale passes shift boxes slightly but
    keep physical centers). Duplicates never produce second blocks — the
    stronger detection wins. Disjoint extra blocks append as new coverage.
    """
    merged = []
    for extra in extra_blocks:
        best: tuple[float, int] | None = None
        for i, base in enumerate(base_blocks):
            base_box, extra_box = base.bbox.model_dump(), extra.bbox.model_dump()
            iou = _bbox_iou(base_box, extra_box)
            if iou < iou_threshold and not (
                _center_in(extra_box, base_box) or _center_in(base_box, extra_box)
            ):
                continue
            if best is None or iou > best[0]:
                best = (iou, i)
        if best is not None:
            i = best[1]
            base = base_blocks[i]
            # Stronger detection wins; equal confidence prefers the base pass.
            if extra.confidence > base.confidence + 1e-9:
                base_blocks[i] = extra
            continue
        merged.append(extra)
    return base_blocks + merged


def _namespace_ids(blocks: list, pass_letter: str) -> None:
    """Give recovery blocks ids that cannot collide with pass A's.

    Each pass parses independently and would otherwise number its blocks
    from 1 again — two blocks sharing an id would corrupt evidence
    references. Recovery ids are namespaced (block_b001, block_c001); pass
    A's ids are never rewritten.
    """
    for index, block in enumerate(blocks, start=1):
        block.id = f"block_{pass_letter.lower()}{index:03d}"


def recover_missing_declarations(
    clean_gray: np.ndarray,
    engine: BaseOCREngine,
    base_blocks: list,
    page_number: int,
    enabled: bool = True,
) -> MultiPassResult:
    """Run recovery passes when pass A lacks mandatory-declaration anchors.

    Pass B re-reads a contrast-only variant of the clean grayscale at base
    scale. Pass C upscales it 2x for genuinely small print. Both are bounded
    (two extra engine calls at most) and their output maps back to base-page
    coordinates before parsing, so merged blocks share the coordinate system
    of pass A evidence.
    """
    if not enabled or (_blocks_have_anchor(base_blocks) and _blocks_have_net_anchor(base_blocks)):
        return MultiPassResult(blocks=base_blocks, passes_run=["A"], extra_time_ms=0)

    started = time.perf_counter()
    passes_run = ["A"]
    current = base_blocks

    pass_b = engine.extract(_contrast_pass(clean_gray))
    b_blocks = [
        b for b in parse_blocks(pass_b, page_number) if b.confidence >= _RECOVERY_MIN_CONFIDENCE
    ]
    _namespace_ids(b_blocks, "B")
    for b in b_blocks:
        b.source_pass = "B"
    current = _merge_blocks(current, b_blocks)
    passes_run.append("B")

    if not _blocks_have_net_anchor(current):
        h, w = clean_gray.shape[:2]
        pass_c_words = _new_words_from(engine.extract(_upscaled(clean_gray)).words, 2.0, 2.0, 0)
        c_blocks = [
            c
            for c in parse_blocks(type(pass_b)(words=pass_c_words, width=w, height=h), page_number)
            if c.confidence >= _RECOVERY_MIN_CONFIDENCE
        ]
        for c in c_blocks:
            c.source_pass = "C"
        _namespace_ids(c_blocks, "C")
        current = _merge_blocks(current, c_blocks)
        passes_run.append("C")

    extra_ms = int((time.perf_counter() - started) * 1000)
    if len(passes_run) > 1:
        logger.info(
            "Multi-pass OCR page %d: passes=%s base=%d merged=%d (%d ms)",
            page_number,
            "+".join(passes_run),
            len(base_blocks),
            len(current),
            extra_ms,
        )
    return MultiPassResult(blocks=current, passes_run=passes_run, extra_time_ms=extra_ms)
