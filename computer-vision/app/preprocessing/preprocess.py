"""Deterministic OCR preprocessing pipeline.

Original image → EXIF orientation → (optional, safe) perspective correction
→ resize → grayscale → contrast → denoise → adaptive threshold (when
beneficial) → light sharpen → OCR-ready matrix.

The input image is never mutated; every step returns new objects.
"""
import cv2
import numpy as np

from app.preprocessing.enhance import (
    adaptive_threshold_when_beneficial,
    enhance_contrast,
    reduce_noise,
    resize_preserving_aspect,
    sharpen_lightly,
    to_grayscale,
)
from app.preprocessing.orientation import correct_orientation


def detect_document_contour(gray: np.ndarray) -> np.ndarray | None:
    """Return the largest quadrilateral contour, or None if no confident one exists."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    area_limit = 0.15 * gray.shape[0] * gray.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contour)
        if area < area_limit:
            continue  # too small to be the document
        hull = cv2.convexHull(contour)
        peri = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        # Require near-convex quadrilateral covering a healthy share of frame.
        if area < 0.30 * gray.shape[0] * gray.shape[1]:
            continue
        return approx.reshape(4, 2).astype(np.float32)
    return None


def perspective_correction(gray: np.ndarray) -> np.ndarray:
    """Warp to the detected document only when confidence is high.

    Detection requires a convex quadrilateral covering ≥30% of the frame whose
    opposite sides are roughly parallel — otherwise the original is returned
    untouched. Conservative by design.
    """
    quad = detect_document_contour(gray)
    if quad is None:
        return gray
    height, width = gray.shape[:2]

    # Order corners: top-left, top-right, bottom-right, bottom-left.
    sums = quad.sum(axis=1)
    diffs = np.diff(quad, axis=1).flatten()
    top_left, bottom_right = quad[np.argmin(sums)], quad[np.argmax(sums)]
    top_right, bottom_left = quad[np.argmin(diffs)], quad[np.argmax(diffs)]

    def dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    top, bottom = dist(top_left, top_right), dist(bottom_left, bottom_right)
    left, right = dist(top_left, bottom_left), dist(top_right, bottom_right)
    if min(top, bottom, left, right) < 40:
        return gray
    # Parallelism check: opposite sides within 25% length of each other.
    if max(top, bottom) > 1.25 * min(top, bottom) or max(left, right) > 1.25 * min(left, right):
        return gray

    out_w, out_h = int(max(top, bottom)), int(max(left, right))
    if out_w < 40 or out_h < 40:
        return gray
    destination = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32
    )
    matrix = cv2.getPerspectiveTransform(quad, destination)
    return cv2.warpPerspective(gray, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC)


def preprocess_for_ocr(image):
    """Run the full pipeline. Returns (ocr_ready_gray_matrix, width, height)."""
    oriented = correct_orientation(image)
    gray = to_grayscale(resize_preserving_aspect(oriented))
    gray = perspective_correction(gray)
    gray = enhance_contrast(gray)
    gray = reduce_noise(gray)
    gray = adaptive_threshold_when_beneficial(gray)
    gray = sharpen_lightly(gray)
    height, width = gray.shape[:2]
    return gray, width, height
