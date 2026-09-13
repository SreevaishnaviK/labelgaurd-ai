"""Deterministic image enhancement steps.

Each step is conservative: the goal is OCR legibility, not beautification.
Fine print must survive, so aggressive operations are avoided.
"""
import cv2
import numpy as np
from PIL import Image

# Longest-edge cap before OCR. Enough resolution for label fine print while
# bounding memory/CPU for large photos.
MAX_OCR_EDGE = 2000
MIN_OCR_EDGE = 640


def resize_preserving_aspect(image: Image.Image) -> Image.Image:
    """Clamp the longest edge into [MIN_OCR_EDGE, MAX_OCR_EDGE], preserving aspect."""
    width, height = image.size
    longest = max(width, height)
    shortest = min(width, height)
    if longest <= MAX_OCR_EDGE and shortest >= MIN_OCR_EDGE:
        return image
    if longest > MAX_OCR_EDGE:
        scale = MAX_OCR_EDGE / longest
    else:
        scale = MIN_OCR_EDGE / shortest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.LANCZOS)


def to_grayscale(image: Image.Image) -> np.ndarray:
    """Convert to a grayscale OpenCV matrix."""
    if image.mode != "L":
        return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    return np.array(image)


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """CLN (contrast-limited) enhancement via CLAHE with a mild clip limit."""
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    return clahe.apply(gray)


def reduce_noise(gray: np.ndarray) -> np.ndarray:
    """Light denoising that keeps character edges crisp."""
    return cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)


def adaptive_threshold_when_beneficial(gray: np.ndarray) -> np.ndarray:
    """Apply adaptive thresholding only when it clearly helps uniformity.

    Heuristic: measure edge strength contrast between the adaptive-threshold
    result and the grayscale. Thresholding is kept only if it reduces
    mid-tone clutter (measured as the fraction of pixels in the ambiguous
    80–200 band) without destroying stroke pixels.
    """
    ambiguous_before = float(np.mean((gray > 80) & (gray < 200)))
    if ambiguous_before < 0.25:
        return gray
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    ink_before = float(np.mean(gray < 128))
    ink_after = float(np.mean(binary < 128))
    # Reject thresholds that erase or flood most of the ink.
    if ink_after < ink_before * 0.4 or ink_after > ink_before * 3.0:
        return gray
    return binary


def sharpen_lightly(gray: np.ndarray) -> np.ndarray:
    """Mild unsharp mask; strong enough for print, gentle on noise."""
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=1.0)
    return cv2.addWeighted(gray, 1.4, blurred, -0.4, 0)
