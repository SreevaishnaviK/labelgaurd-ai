"""Phase 9B: conservative visual declaration-symbol detection.

The legal FSSAI mark is a colored ring around a concentric filled disk. The
detector must classify ONLY that enclosure geometry — never ordinary green
packaging graphics — and return an empty result (INSUFFICIENT EVIDENCE)
rather than a guess when nothing qualifies.
"""
import cv2
import numpy as np
import pytest

from app.evidence.symbols import detect_declaration_symbols

GREEN = (80, 170, 60)  # BGR
BROWN = (40, 60, 90)  # BGR — the non-veg mark's red/brown


def _veg_symbol(size=120, color=GREEN, ring=5) -> np.ndarray:
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 3, color, ring)
    cv2.circle(img, (size // 2, size // 2), size // 6, color, -1)
    return img


def _nonveg_symbol(size=120) -> np.ndarray:
    return _veg_symbol(size=size, color=BROWN)


def _solid_disk(size=120, color=GREEN) -> np.ndarray:
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 3, color, -1)
    return img


def _leaf(size=200, color=GREEN) -> np.ndarray:
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.ellipse(img, (size // 2, size // 2), (size // 3, size // 8), 30, 0, 360, color, -1)
    return img


def _label_with(art, y=360, x=660) -> np.ndarray:
    """Place artwork on a white label canvas, away from the frame border."""
    canvas = np.full((480, 800, 3), 255, np.uint8)
    h, w = art.shape[:2]
    canvas[y : y + h, x : x + w] = art
    return canvas


def _near(hit_bbox, x, y, tol=25) -> bool:
    """The mark's component sits a few px inside the placed art rect."""
    return abs(hit_bbox["x"] - x) <= tol and abs(hit_bbox["y"] - y) <= tol


# ---------------------------------------------------------------- positive

def test_clear_vegetarian_symbol_detected():
    hits = detect_declaration_symbols(_label_with(_veg_symbol()))
    assert len(hits) == 1
    hit = hits[0]
    assert hit["declaration"] == "vegetarian"
    assert hit["confidence"] > 0.5
    # Real bbox at the artwork's location in the label's coordinate system (§11).
    assert _near(hit["bbox"], 660, 360)
    assert 20 <= hit["bbox"]["width"] <= 100


def test_clear_non_vegetarian_symbol_detected():
    hits = detect_declaration_symbols(_label_with(_nonveg_symbol()))
    assert len(hits) == 1
    assert hits[0]["declaration"] == "non_vegetarian"
    assert _near(hits[0]["bbox"], 660, 360)


def test_detection_does_not_depend_on_ocr():
    """A pure-white canvas with ONLY the symbol (no text at all) still
    classifies — the detector is visual, not textual (§18H)."""
    hits = detect_declaration_symbols(_veg_symbol(size=160))
    assert len(hits) == 1
    assert hits[0]["declaration"] == "vegetarian"


def test_mutually_exclusive_single_strongest_classification():
    """Green and brown marks together → exactly one winner (the legal mark
    is a single declaration)."""
    canvas = np.full((300, 300, 3), 255, np.uint8)
    veg, nonveg = _veg_symbol(size=90), _nonveg_symbol(size=90)
    canvas[30:120, 30:120] = veg
    canvas[150:240, 150:240] = nonveg
    hits = detect_declaration_symbols(canvas)
    assert len(hits) == 1
    assert hits[0]["declaration"] in {"vegetarian", "non_vegetarian"}


# ---------------------------------------------------------------- negative

def test_solid_green_disk_is_not_a_symbol():
    """A filled disk has color at every radius — no ring gap → rejected."""
    assert detect_declaration_symbols(_label_with(_solid_disk())) == []


def test_green_leaf_is_not_a_symbol():
    """Unrelated green packaging art (elongated, non-circular) must never
    become a vegetarian classification (§18E — the FarmBite leaves)."""
    leaf = _leaf(size=160)
    assert detect_declaration_symbols(_label_with(leaf, y=260, x=620)) == []


def test_hollow_ring_without_inner_disk_is_not_a_symbol():
    img = np.full((120, 120, 3), 255, np.uint8)
    cv2.circle(img, (60, 60), 40, GREEN, 5)  # ring only — no core
    assert detect_declaration_symbols(img) == []


def test_grayscale_image_is_insufficient_evidence():
    """Color is required: a grayscale source cannot support a color-based
    classification and must NOT guess."""
    gray = cv2.cvtColor(_veg_symbol(), cv2.COLOR_BGR2GRAY)
    assert detect_declaration_symbols(gray) == []


def test_empty_image_is_insufficient_evidence():
    assert detect_declaration_symbols(np.full((100, 100, 3), 255, np.uint8)) == []


def test_none_image_is_insufficient_evidence():
    assert detect_declaration_symbols(None) == []


def test_border_touching_art_is_rejected():
    """Color regions running off the frame are background art, not a mark."""
    img = np.full((200, 200, 3), 255, np.uint8)
    cv2.circle(img, (0, 0), 60, GREEN, 6)
    cv2.circle(img, (0, 0), 30, GREEN, -1)
    assert detect_declaration_symbols(img) == []


# ---------------------------------------------------------------- confidence

def test_confidence_is_not_a_fixed_value():
    """Confidence must reflect geometry/color strength, not a constant."""
    crisp = detect_declaration_symbols(_veg_symbol(size=120))[0]["confidence"]
    faint = detect_declaration_symbols(
        _label_with(_veg_symbol(size=90, color=(110, 190, 100), ring=3))
    )[0]["confidence"]
    assert crisp != faint
    assert 0.0 < faint < 1.0 and 0.0 < crisp < 1.0


@pytest.mark.parametrize("size", [60, 90, 140])
def test_symbol_detected_across_sizes(size):
    """Generic detection — no hard-coded FarmBite coordinates or size."""
    canvas = np.full((480, 800, 3), 255, np.uint8)
    art = _veg_symbol(size=size)
    y, x = min(360, 480 - size - 10), 380  # keep the mark off the frame border
    canvas[y : y + size, x : x + size] = art
    hits = detect_declaration_symbols(canvas)
    assert len(hits) == 1 and hits[0]["declaration"] == "vegetarian"
    assert _near(hits[0]["bbox"], x, y)
