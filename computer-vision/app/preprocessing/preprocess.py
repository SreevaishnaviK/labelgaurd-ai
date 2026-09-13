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
    """Return a confidently-angled document quadrilateral, or None.

    A rectangular label photographed straight-on produces a quad hugging the
    frame edges — warping that merely crops margins and destroys text. Only a
    genuinely tilted document (corners clearly pulled away from the frame)
    justifies correction.
    """
    height, width = gray.shape[:2]
    frame_area = float(height * width)
    margin = 0.08  # required gap between document corners and the frame
    min_gap_x = margin * width
    min_gap_y = margin * height

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    area_limit = 0.15 * frame_area
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contour)
        if area < area_limit or area < 0.30 * frame_area:
            continue  # too small to be the document
        hull = cv2.convexHull(contour)
        peri = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        quad = approx.reshape(4, 2).astype(np.float32)
        # Every corner must sit clearly inside the frame — a straight-on photo
        # has corners ON the frame, which is not a perspective problem.
        if (
            quad[:, 0].min() < min_gap_x
            or quad[:, 0].max() > width - min_gap_x
            or quad[:, 1].min() < min_gap_y
            or quad[:, 1].max() > height - min_gap_y
        ):
            continue
        return quad
    return None


def perspective_correction(gray: np.ndarray) -> np.ndarray:
    """Warp to the detected document only when confidence is high.

    Detection requires a convex quadrilateral covering ≥30% of the frame whose
    corners sit clearly inside it (a genuinely tilted document) and whose
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


def preprocess_for_ocr(image) -> tuple[np.ndarray, int, int, bool]:
    """Run the full pipeline.

    Returns (ocr_ready_gray_matrix, width, height, warped) where `warped` is
    True only when perspective correction changed the geometry — consumers
    that overlay coordinates on the ORIGINAL image must treat those
    coordinates as invalid for warped pages.
    """
    oriented = correct_orientation(image)
    gray = to_grayscale(resize_preserving_aspect(oriented))
    original_shape = gray.shape[:2]
    gray = perspective_correction(gray)
    warped = gray.shape[:2] != original_shape
    gray = enhance_contrast(gray)
    gray = reduce_noise(gray)
    gray = adaptive_threshold_when_beneficial(gray)
    gray = sharpen_lightly(gray)
    height, width = gray.shape[:2]
    return gray, width, height, warped
