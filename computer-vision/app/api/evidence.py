"""POST /api/v1/evidence/analyze — visual evidence over persisted OCR data.

The backend sends the processed-image references and OCR blocks it already
stores; this endpoint measures — it never re-runs OCR and never receives the
original upload. Measurements are objective values with methods; legal
interpretation lives in the Legal Engine.
"""
import logging
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.evidence.declarations import declaration_regions
from app.evidence.geometry import contrast_metric, new_evidence_id, readability_metrics
from app.evidence.pdp import detect_candidate_pdp, detect_package_boundary, physical_area_cm2
from app.schemas.vision import EvidenceAnalyzeRequest, EvidenceAnalyzeSuccess, EvidenceItem

logger = logging.getLogger(__name__)

router = APIRouter()

# Blocks below this OCR confidence carry too little signal to measure.
_MIN_BLOCK_CONFIDENCE = 40.0


def _load_processed_gray(processed_path: str) -> np.ndarray:
    root = Path(get_settings().upload_dir)
    path = root / processed_path
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "PROCESSED_IMAGE_MISSING", "message": f"Processed image not found: {processed_path}"},
        )
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "PROCESSED_IMAGE_UNREADABLE", "message": f"Could not read processed image: {processed_path}"},
        )
    return gray


def _boundary_items(gray: np.ndarray, page_number: int) -> list[EvidenceItem]:
    bbox, confidence = detect_package_boundary(gray)
    if bbox is None:
        return [
            EvidenceItem(
                evidence_id=new_evidence_id(),
                evidence_type="BOUNDARY",
                page_number=page_number,
                value="not detected",
                confidence=0.0,
                method="contour_quadrilateral",
                verification_status="INSUFFICIENT_EVIDENCE",
                note="No confident package/label boundary in this image.",
            )
        ]
    return [
        EvidenceItem(
            evidence_id=new_evidence_id(),
            evidence_type="BOUNDARY",
            page_number=page_number,
            bbox=bbox,
            value=bbox["width"] * bbox["height"],
            unit="px2",
            confidence=round(confidence, 2),
            method="contour_quadrilateral",
            verification_status="AUTOMATED",
        )
    ]


def _pdp_items(
    gray: np.ndarray,
    page_number: int,
    blocks: list[dict],
    calibration,
) -> list[EvidenceItem]:
    bbox, confidence, method = detect_candidate_pdp(gray, blocks)
    if bbox is None:
        return [
            EvidenceItem(
                evidence_id=new_evidence_id(),
                evidence_type="PDP_AREA",
                page_number=page_number,
                confidence=0.0,
                method="text_band_prominence",
                verification_status="INSUFFICIENT_EVIDENCE",
                note="No text available to locate a candidate principal display panel.",
            )
        ]
    items = [
        EvidenceItem(
            evidence_id=new_evidence_id(),
            evidence_type="PDP_AREA",
            page_number=page_number,
            bbox=bbox,
            value=bbox["width"] * bbox["height"],
            unit="px2",
            confidence=confidence,
            method=method,
            verification_status="AUTOMATED",
            note="Candidate Principal Display Panel — not a legal determination.",
        )
    ]
    if calibration is not None:
        items.append(
            EvidenceItem(
                evidence_id=new_evidence_id(),
                evidence_type="PDP_AREA",
                page_number=page_number,
                bbox=bbox,
                value=physical_area_cm2(bbox, calibration.px_per_mm),
                unit="cm2",
                confidence=confidence,
                method=f"calibrated_scale ({calibration.source})",
                verification_status="AUTOMATED",
            )
        )
    return items


def _text_height_items(
    gray: np.ndarray,
    page_number: int,
    blocks: list[dict],
    calibration,
) -> list[EvidenceItem]:
    if not blocks:
        return []
    tallest = max(blocks, key=lambda b: b["bbox"]["height"])
    items = [
        EvidenceItem(
            evidence_id=new_evidence_id(),
            evidence_type="TEXT_HEIGHT",
            page_number=page_number,
            bbox=tallest["bbox"],
            value=tallest["bbox"]["height"],
            unit="px",
            confidence=round(tallest["confidence"] / 100.0, 3),
            method="ocr_block_bbox",
            verification_status="AUTOMATED",
            ocr_block_id=tallest["id"],
            note="Estimated text height in pixels — not a physical millimetre value.",
        )
    ]
    if calibration is not None:
        items.append(
            EvidenceItem(
                evidence_id=new_evidence_id(),
                evidence_type="TEXT_HEIGHT",
                page_number=page_number,
                bbox=tallest["bbox"],
                value=round(tallest["bbox"]["height"] / calibration.px_per_mm, 2),
                unit="mm",
                confidence=round(tallest["confidence"] / 100.0, 3),
                method=f"calibrated_scale ({calibration.source})",
                verification_status="AUTOMATED",
                ocr_block_id=tallest["id"],
            )
        )
    return items


def _readability_contrast_items(gray: np.ndarray, page_number: int, blocks: list[dict]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for block in blocks[:12]:  # cap cost: the most prominent bands suffice
        bbox = block["bbox"]
        try:
            metrics = readability_metrics(gray, bbox)
        except ValueError:
            continue  # degenerate region — skipped, not guessed
        items.append(
            EvidenceItem(
                evidence_id=new_evidence_id(),
                evidence_type="READABILITY",
                page_number=page_number,
                bbox=bbox,
                value=round(metrics.laplacian_variance, 2),
                unit="laplacian_variance",
                confidence=round(block["confidence"] / 100.0, 3),
                method="variance_of_laplacian",
                verification_status="AUTOMATED",
                ocr_block_id=block["id"],
                note=f"local rms contrast {metrics.local_contrast:.3f}",
            )
        )
        contrast = contrast_metric(gray, bbox)
        if contrast["contrast"] is not None:
            items.append(
                EvidenceItem(
                    evidence_id=new_evidence_id(),
                    evidence_type="CONTRAST",
                    page_number=page_number,
                    bbox=bbox,
                    value=contrast["contrast"],
                    unit="normalized_luminance_delta",
                    confidence=round(block["confidence"] / 100.0, 3),
                    method=contrast["method"],
                    verification_status="AUTOMATED",
                    ocr_block_id=block["id"],
                )
            )
    return items


@router.post("/api/v1/evidence/analyze", response_model=EvidenceAnalyzeSuccess)
def analyze_evidence(request: EvidenceAnalyzeRequest) -> EvidenceAnalyzeSuccess:
    started = time.perf_counter()
    evidence: list[EvidenceItem] = []
    blocks_by_id: dict[str, dict] = {}
    for page in request.pages:
        gray = _load_processed_gray(page.processed_path)
        blocks = [b.model_dump() for b in page.blocks if b.confidence >= _MIN_BLOCK_CONFIDENCE]
        blocks_by_id.update({b["id"]: {**b, "page_number": page.page_number} for b in blocks})
        evidence.extend(_boundary_items(gray, page.page_number))
        evidence.extend(_pdp_items(gray, page.page_number, blocks, request.calibration))
        evidence.extend(_text_height_items(gray, page.page_number, blocks, request.calibration))
        evidence.extend(_readability_contrast_items(gray, page.page_number, blocks))
    evidence.extend(
        EvidenceItem(**region)
        for region in declaration_regions(
            [f.model_dump() for f in request.fields], blocks_by_id
        )
    )
    logger.info(
        "Evidence analysis for %s: %d items in %d ms",
        request.inspection_id,
        len(evidence),
        int((time.perf_counter() - started) * 1000),
    )
    return EvidenceAnalyzeSuccess(inspection_id=request.inspection_id, evidence=evidence)
