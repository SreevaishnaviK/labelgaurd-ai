"""Preprocessing pipeline tests (no OCR dependency)."""
import io

import numpy as np
from PIL import Image

from app.preprocessing.image_loader import decode_image
from app.preprocessing.orientation import correct_orientation
from app.preprocessing.preprocess import preprocess_for_ocr


def _image_with_exif(orientation: int) -> Image.Image:
    image = Image.new("RGB", (120, 60), "white")
    exif = image.getexif()
    exif[0x0112] = orientation  # orientation tag
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", exif=exif)
    return Image.open(io.BytesIO(buffer.getvalue()))


def test_exif_orientation_rotates() -> None:
    sideways = _image_with_exif(6)  # rotate 90 CW
    corrected = correct_orientation(sideways)
    assert corrected.size == (60, 120)


def test_exif_absent_is_noop() -> None:
    plain = Image.new("RGB", (120, 60), "white")
    assert correct_orientation(plain).size == (120, 60)


def test_orientation_idempotent() -> None:
    sideways = _image_with_exif(6)
    once = correct_orientation(sideways)
    twice = correct_orientation(once)
    assert once.size == twice.size


def test_original_not_mutated() -> None:
    image = _image_with_exif(6)
    before = image.size
    correct_orientation(image)
    assert image.size == before


def test_pipeline_returns_valid_matrix() -> None:
    image = Image.new("RGB", (400, 200), "white")
    gray, width, height = preprocess_for_ocr(image)
    assert gray.ndim == 2
    assert (height, width) == gray.shape
    assert width > 0 and height > 0


def test_pipeline_does_not_mutate_input() -> None:
    image = Image.new("RGB", (400, 200), "white")
    snapshot = image.tobytes()
    preprocess_for_ocr(image)
    assert image.tobytes() == snapshot


def test_pipeline_deterministic() -> None:
    image = Image.new("RGB", (400, 200), "white")
    a, *_ = preprocess_for_ocr(image)
    b, *_ = preprocess_for_ocr(image)
    assert np.array_equal(a, b)


def test_small_image_upscaled_to_min_edge() -> None:
    image = Image.new("RGB", (100, 50), "white")
    _, width, height = preprocess_for_ocr(image)
    assert max(width, height) >= 640  # MIN_OCR_EDGE respected
