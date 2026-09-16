"""Candidate Principal Display Panel and package/label boundary detection.

Conservative by design: an arbitrary detected rectangle is never claimed to
be legally the PDP — the output is a "Candidate Principal Display Panel"
with its detection method and confidence. Pixels are never converted to
physical units without a supplied calibration.
"""
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# A candidate PDP must be a substantial part of the label but not the whole
# frame (which would just be the document boundary, not a panel).
_MIN_PANEL_FRACTION = 0.10
_MAX_PANEL_FRACTION = 0.92


def detect_package_boundary(gray: np.ndarray) -> tuple[dict | None, float]:
    """Largest confident quadrilateral bounding the label/package, or None.

    Reuses the contour approach from preprocessing's perspective detector but
    WITHOUT the tilted-document restriction: a straight-on label that fills
    the frame is a perfectly good boundary. Returns (bbox_dict|None, conf).
    """
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: tuple[dict, float] | None = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contour)
        if area < 0.30 * frame_area:
            continue
        hull = cv2.convexHull(contour)
        x, y, w, h = cv2.boundingRect(hull)
        # How completely the hull fills its bounding box — a clean rectangle
        # scores high; ragged edges score lower.
        fill = area / float(w * h)
        if fill < 0.55:
            continue
        candidate = {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
        if best is None or w * h > best[0]["width"] * best[0]["height"]:
            best = (candidate, min(0.95, 0.5 + 0.45 * fill))
    return best if best else (None, 0.0)


def detect_candidate_pdp(gray: np.ndarray, blocks: list[dict]) -> tuple[dict | None, float, str]:
    """Candidate PDP = the text band containing the most prominent text.

    "Prominent" is measured as glyph stroke height × block width (the visual
    mass of the title band) — never just the first block. Falls back to the
    full ink extent of all text when no band stands out. Returns
    (bbox|None, confidence, method).
    """
    if not blocks:
        return None, 0.0, "text_band_prominence"
    height, width = gray.shape[:2]
    by_band: dict[int, list[dict]] = {}
    for block in blocks:
        band = int(block["bbox"]["y"] // max(1, height // 8))
        by_band.setdefault(band, []).append(block)

    def mass(entries: list[dict]) -> float:
        return sum(b["bbox"]["width"] * max(b["bbox"]["height"], 1) for b in entries)

    best_band = max(by_band, key=lambda k: mass(by_band[k]))
    entries = by_band[best_band]
    x1 = min(b["bbox"]["x"] for b in entries)
    y1 = min(b["bbox"]["y"] for b in entries)
    x2 = max(b["bbox"]["x"] + b["bbox"]["width"] for b in entries)
    y2 = max(b["bbox"]["y"] + b["bbox"]["height"] for b in entries)
    panel_area = (x2 - x1) * (y2 - y1)
    frame_area = float(width * height)
    fraction = panel_area / frame_area
    if fraction < _MIN_PANEL_FRACTION or fraction > _MAX_PANEL_FRACTION:
        # Degenerate band (one tiny strip or nearly the whole page) — the
        # honest answer is a full-extent candidate with lower confidence.
        x1 = min(b["bbox"]["x"] for b in blocks)
        y1 = min(b["bbox"]["y"] for b in blocks)
        x2 = max(b["bbox"]["x"] + b["bbox"]["width"] for b in blocks)
        y2 = max(b["bbox"]["y"] + b["bbox"]["height"] for b in blocks)
        return (
            {"x": int(x1), "y": int(y1), "width": int(x2 - x1), "height": int(y2 - y1)},
            0.35,
            "text_extent_fallback",
        )
    confidence = min(0.85, 0.45 + 0.4 * (mass(entries) / max(1.0, mass(blocks))))
    return (
        {"x": int(x1), "y": int(y1), "width": int(x2 - x1), "height": int(y2 - y1)},
        round(confidence, 2),
        "text_band_prominence",
    )


def physical_area_cm2(bbox: dict, px_per_mm: float) -> float:
    """Physical panel area from a calibrated scale. Never called without one."""
    width_mm = bbox["width"] / px_per_mm
    height_mm = bbox["height"] / px_per_mm
    return round(width_mm * height_mm, 2)
