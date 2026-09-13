"""CV storage helpers: persist the processed (OCR-ready) image per page.

The original upload is never touched; this writes a separate processed PNG
under uploads/processed/ so evidence of what OCR actually saw survives.
"""
from pathlib import Path

import numpy as np
from PIL import Image


def save_processed_image(page_root: Path, page_number: int, image: np.ndarray) -> str:
    """Write the page's processed matrix as PNG under page_root; return filename."""
    page_root.mkdir(parents=True, exist_ok=True)
    filename = f"page-{page_number:02d}.png"
    Image.fromarray(image).save(page_root / filename, format="PNG")
    return filename
