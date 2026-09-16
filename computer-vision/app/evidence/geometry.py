"""Text geometry, readability, and contrast measurements.

Objective image-quality metrics only: pixel heights stay pixels, contrast and
blur are raw numbers with their method recorded. No metric is ever mapped to
a legal conclusion here — that is the Legal Engine's job.
"""
import logging
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ReadabilityMetrics:
    """Raw readability measurements for a region."""

    laplacian_variance: float  # blur/sharpness proxy (higher = sharper)
    local_contrast: float  # rms contrast of the region's grayscale (0-1)


def _crop(image: np.ndarray, bbox: dict) -> np.ndarray:
    height, width = image.shape[:2]
    x = max(0, int(bbox.get("x", 0)))
    y = max(0, int(bbox.get("y", 0)))
    x2 = min(width, x + max(0, int(bbox.get("width", 0))))
    y2 = min(height, y + max(0, int(bbox.get("height", 0))))
    if x2 - x < 2 or y2 - y < 2:
        raise ValueError("region outside the image")
    return image[y:y2, x:x2]


def readability_metrics(gray: np.ndarray, bbox: dict) -> ReadabilityMetrics:
    """Blur + local contrast for a region of a grayscale page image."""
    region = _crop(gray, bbox)
    laplacian_variance = float(cv2.Laplacian(region, cv2.CV_64F).var())
    local_contrast = float(np.std(region.astype(np.float64) / 255.0))
    return ReadabilityMetrics(laplacian_variance=laplacian_variance, local_contrast=local_contrast)


def contrast_metric(gray: np.ndarray, bbox: dict) -> dict:
    """Objective foreground/background luminance contrast for a text region.

    Method: split the region's grayscale into ink/background by Otsu's
    threshold and report the absolute mean-luminance difference normalized to
    0-1. This is a measurement, not a threshold judgment.
    """
    region = _crop(gray, bbox)
    _, binary = cv2.threshold(region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = region[binary == 0]
    background = region[binary == 255]
    if ink.size == 0 or background.size == 0:
        return {"contrast": None, "method": "otsu_luminance_split", "degenerate": True}
    ink_level = float(np.mean(ink)) / 255.0
    background_level = float(np.mean(background)) / 255.0
    return {
        "contrast": round(abs(background_level - ink_level), 4),
        "method": "otsu_luminance_split",
        "degenerate": False,
    }


def new_evidence_id() -> str:
    return f"ev_{uuid.uuid4().hex[:12]}"
