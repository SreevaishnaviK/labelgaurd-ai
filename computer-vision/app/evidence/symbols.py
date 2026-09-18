"""Visual declaration-symbol detection (Phase 9B).

The vegetarian / non-vegetarian declaration on Indian packaged food is a
colored symbol — a green or red/brown ring around a filled disk (optionally
with a letter inside) — not OCR text. This detector is deliberately
conservative and entirely deterministic (OpenCV, no models):

1. hue-mask the image for the regulation-recognized colors (green; red/brown),
2. find compact circular components that do not touch the frame border,
3. keep only an enclosure structure: a filled core of the same color with a
   visible BACKGROUND GAP between core and outer edge (concentric ring +
   inner disk). The gap is the discriminator — a plain green disk/logo dot
   has color at every radius and is rejected; an elongated leaf fails the
   circularity gate.

Color alone is never sufficient (§18E): an unrelated green leaf fails the
concentric-enclosure test and produces no classification. Confidence
combines geometry (circularity, concentricity, size sanity) with color
saturation strength — it is detection confidence, not legal weight.

The detector reports only what it sees. Whether a vegetarian declaration is
legally required, or correctly placed, remains the Legal Engine's question.
"""
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# HSV windows (OpenCV hue 0-179): green; red wraps the hue origin; brown is
# dark, low-saturation red-orange.
_COLOR_WINDOWS = {
    "vegetarian": [((35, 60, 40), (95, 255, 255))],
    "non_vegetarian": [
        ((0, 70, 60), (12, 255, 255)),
        ((168, 70, 60), (180, 255, 255)),
        ((5, 60, 40), (25, 255, 200)),
    ],
}

# Component gates: a declaration symbol is a small-to-medium mark, clearly
# inside the frame (border-touching color regions are background art).
_MIN_AREA = 250
_MAX_SIDE = 160
# Circularity of the outer contour (1.0 = perfect circle).
_MIN_CIRCULARITY = 0.55
# The declaration symbol is a circle: its bounding box must be near-square.
# Elongated green packaging graphics (leaves, banners) fail this gate.
_MAX_BBOX_ASPECT = 1.30
# Concentricity: inner centroid within this fraction of the outer radius.
_CONCENTRIC_FRACTION = 0.45
# The inner disk must fill a visible part of the ring's interior.
_MIN_INNER_AREA_RATIO = 0.04
# Enclosure gate: between 55% and 80% of the outer radius the mask must be
# mostly BACKGROUND (the white gap between ring and inner disk). A solid
# disk/logo dot is colored at every radius and is rejected here.
_ANNULUS_INNER_FRACTION = 0.55
_ANNULUS_OUTER_FRACTION = 0.80
_MAX_ANNULUS_COLOR_FRACTION = 0.55


def _circularity(contour) -> float:
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return 0.0
    return float(4 * np.pi * cv2.contourArea(contour) / (perimeter * perimeter))


def _component_masked_mean(hsv: np.ndarray, mask: np.ndarray, ys: int, xs: int, h: int, w: int) -> tuple[float, float]:
    region = hsv[ys : ys + h, xs : xs + w]
    m = mask[ys : ys + h, xs : xs + w] > 0
    if not m.any():
        return 0.0, 0.0
    return float(region[..., 1][m].mean()), float(region[..., 2][m].mean())


def _detect_for_color(hsv: np.ndarray, windows, border: int) -> list[dict]:
    height, width = hsv.shape[:2]
    found: list[dict] = []
    for lo, hi in windows:
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < _MIN_AREA or w > _MAX_SIDE or h > _MAX_SIDE or h < 12:
                continue
            if max(w, h) / min(w, h) > _MAX_BBOX_ASPECT:
                continue  # near-square gate: leaves/banners are elongated
            if x <= border or y <= border or x + w >= width - border or y + h >= height - border:
                continue
            comp = (labels == i).astype(np.uint8)
            contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            outer = max(contours, key=cv2.contourArea)
            circularity = _circularity(outer)
            if circularity < _MIN_CIRCULARITY:
                continue
            # Inner disk: same-colored pixels well inside the component's
            # centroid (the symbol's filled center), vs a hollow ring.
            (cx, cy), outer_radius = cv2.minEnclosingCircle(outer)
            probe_r = max(2, int(outer_radius * 0.35))
            px, py = int(round(cx)), int(round(cy))
            if px - probe_r < 0 or py - probe_r < 0 or px + probe_r >= width or py + probe_r >= height:
                continue
            core = np.zeros((height, width), np.uint8)
            cv2.circle(core, (px, py), probe_r, 1, -1)
            core_pixels = int(mask[core > 0].size and (mask[core > 0] > 0).sum())
            if core_pixels < _MIN_INNER_AREA_RATIO * area:
                continue
            # Ring-gap test: sample the annulus between the core and the
            # outer edge; an enclosure has background there, a solid disk
            # does not.
            annulus = np.zeros((height, width), np.uint8)
            cv2.circle(annulus, (px, py), max(3, int(outer_radius * _ANNULUS_OUTER_FRACTION)), 1, -1)
            cv2.circle(annulus, (px, py), max(2, int(outer_radius * _ANNULUS_INNER_FRACTION)), 0, -1)
            annulus_pixels = int((annulus > 0).sum())
            if annulus_pixels == 0:
                continue
            annulus_color = int(((mask > 0) & (annulus > 0)).sum())
            annulus_color_fraction = annulus_color / annulus_pixels
            if annulus_color_fraction > _MAX_ANNULUS_COLOR_FRACTION:
                continue  # color at every radius → a solid disk, not the symbol
            saturation, value = _component_masked_mean(hsv, mask, y, x, h, w)
            concentricity = float(
                np.hypot(cx - centroids[i][0], cy - centroids[i][1]) / max(1.0, outer_radius)
            )
            found.append(
                {
                    "bbox": {"x": x, "y": y, "width": w, "height": h},
                    "circularity": round(circularity, 3),
                    "concentricity": round(concentricity, 3),
                    "saturation": saturation,
                    "value": value,
                    "core_ratio": round(core_pixels / max(1, area), 3),
                    "gap_purity": round(1.0 - annulus_color_fraction, 3),
                }
            )
    return found


def _confidence(hit: dict) -> float:
    """Detection confidence from geometry and color strength — no fixed 95%."""
    geometry = (
        0.45 * hit["circularity"]
        + 0.25 * (1.0 - min(1.0, hit["concentricity"] * 2))
        + 0.15 * min(1.0, hit["core_ratio"] * 5)
        + 0.15 * hit["gap_purity"]
    )
    color = min(1.0, hit["saturation"] / 200.0)
    return round(max(0.0, min(1.0, 0.75 * geometry + 0.25 * color)), 3)


def detect_declaration_symbols(color_image: np.ndarray) -> list[dict]:
    """Detect vegetarian / non-vegetarian symbols in a color label image.

    Returns one hit per symbol (strongest per class when several overlap),
    each with a bbox in the original image's coordinate system. An empty
    list means INSUFFICIENT EVIDENCE — never a guess.
    """
    if color_image is None or color_image.size == 0:
        return []
    if color_image.ndim == 2:
        return []  # color required; a grayscale source cannot support this
    hsv = cv2.cvtColor(color_image, cv2.COLOR_BGR2HSV)
    height, width = hsv.shape[:2]
    border = max(2, min(width, height) // 100)

    classifications: dict[str, dict] = {}
    for declaration, windows in _COLOR_WINDOWS.items():
        best = None
        for hit in _detect_for_color(hsv, windows, border):
            score = _confidence(hit)
            if best is None or score > best[0]:
                best = (score, hit)
        if best is not None:
            classifications[declaration] = {"confidence": best[0], **best[1]}
    # Mutually exclusive declaration: keep the single strongest class.
    if len(classifications) > 1:
        winner = max(classifications, key=lambda k: classifications[k]["confidence"])
        classifications = {winner: classifications[winner]}
    return [
        {"declaration": declaration, **payload} for declaration, payload in classifications.items()
    ]
