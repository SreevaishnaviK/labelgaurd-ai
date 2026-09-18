"""Visual evidence service (Phase 7).

Runs CV evidence analysis over an inspection's persisted OCR data, stores
the measurements, and feeds them into legal-engine evaluation inputs.
Provenance rules enforced here:
- pixel values stay pixels (never presented as physical units);
- physical values exist only when a real calibration produced them, and no
  calibration is ever invented by this service;
- measured_quantity is NEVER produced from an image — quantity measurement
  must come from a genuine physical source.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import computer_vision_client
from app.clients.computer_vision_client import CVRejectionError, CVServiceError  # re-exported for API handlers
from app.models.inspection import (
    ExtractedField,
    Inspection,
    OCRDocument,
    OCRBlock,
    VisualEvidenceRecord,
)

logger = logging.getLogger(__name__)


def _pages_payload(inspection: Inspection, session: Session) -> list[dict]:
    """Persisted OCR pages as the CV evidence API expects them."""
    pages = []
    for doc in sorted(
        session.execute(
            select(OCRDocument)
            .where(OCRDocument.inspection_id == inspection.id)
            .order_by(OCRDocument.page_number)
        ).scalars(),
        key=lambda d: d.page_number,
    ):
        blocks = [
            {
                "id": b.block_id,
                "text": b.text,
                "confidence": float(b.confidence),
                "bbox": {"x": b.x, "y": b.y, "width": b.width, "height": b.height},
                "line_number": b.line_number,
                "block_number": b.block_number,
                "page_number": b.page_number,
                # Pass provenance ("A"/"B"/"C") — carried so evidence and
                # extraction can distinguish base-pipeline reads from
                # recovery-pass reads. Missing on pre-9B rows.
                "source_pass": b.source_pass,
            }
            for b in session.execute(
                select(OCRBlock)
                .where(OCRBlock.inspection_id == inspection.id)
                .where(OCRBlock.page_number == doc.page_number)
                .order_by(OCRBlock.id)
            ).scalars()
        ]
        pages.append(
            {
                "page_number": doc.page_number,
                "width": doc.width,
                "height": doc.height,
                "processed_path": doc.processed_path or "",
                "blocks": blocks,
            }
        )
    return pages


def _fields_payload(session: Session, inspection: Inspection) -> list[dict]:
    fields = (
        session.execute(
            select(ExtractedField)
            .where(ExtractedField.inspection_id == inspection.id)
            .order_by(ExtractedField.id)
        )
        .scalars()
        .all()
    )
    return [
        {
            "field_name": field.field_name,
            "evidence": [
                {"ocr_block_id": ref.ocr_block_id, "page_number": ref.page_number}
                for ref in field.evidence
            ],
        }
        for field in fields
    ]


def run_evidence_analysis(session: Session, inspection: Inspection) -> list[VisualEvidenceRecord]:
    """Call the CV evidence service and persist the measurements.

    Regenerates evidence rows each run (older rows for this inspection are
    replaced) so re-analysis reflects the current image data. Raises
    CVServiceError/CVRejectionError on failure — the caller decides how to
    degrade (the inspection itself is never destroyed).
    """
    pages = _pages_payload(inspection, session)
    if not any(page["processed_path"] for page in pages):
        logger.info("No processed images for %s; skipping evidence analysis", inspection.inspection_id)
        return []
    result = computer_vision_client.analyze_evidence(
        inspection_id=inspection.inspection_id,
        pages=pages,
        fields=_fields_payload(session, inspection),
        # The CV service shares the uploads volume; symbol detection needs
        # the color original (binarized OCR images carry no hue).
        original_path=inspection.file_path,
    )
    # Replace prior rows: evidence reflects the latest analysis.
    for old in session.execute(
        select(VisualEvidenceRecord).where(VisualEvidenceRecord.inspection_id == inspection.id)
    ).scalars():
        session.delete(old)
    records: list[VisualEvidenceRecord] = []
    for item in result.evidence:
        value = item.get("value")
        records.append(
            VisualEvidenceRecord(
                inspection=inspection,
                evidence_id=item["evidence_id"],
                evidence_type=item["evidence_type"],
                page_number=int(item.get("page_number", 1)),
                bbox_json=item.get("bbox"),
                value_numeric=float(value) if isinstance(value, (int, float)) else None,
                value_text=value if isinstance(value, str) else None,
                unit=item.get("unit"),
                confidence=item.get("confidence"),
                method=item.get("method", ""),
                verification_status=item.get("verification_status", "AUTOMATED"),
                ocr_block_id=item.get("ocr_block_id"),
                ocr_block_ids=item.get("ocr_block_ids"),
                field_name=item.get("field_name"),
                note=item.get("note"),
            )
        )
        session.add(records[-1])
    session.flush()
    return records


def compose_symbol_field(session: Session, inspection: Inspection) -> bool:
    """Compose the ``vegetarian_non_vegetarian`` field from symbol evidence.

    A visual-symbol classification is NOT OCR text, so it does not belong to
    the AI extraction pipeline — but officers and the UI reason about it as
    a structured field. This composes one field row beside the extracted
    ones, with the method naming the visual detector and the value JSON
    carrying the evidence_id as provenance. It never fabricates an OCR
    reference, and only symbol evidence with a real bbox classification
    (verification_status AUTOMATED, a known declaration) produces a
    ``detected`` row — anything else stays absent rather than guessed.
    Returns True when a row was written.
    """
    from app.models.inspection import ExtractedField  # local: avoids import cycle

    symbol = session.execute(
        select(VisualEvidenceRecord)
        .where(VisualEvidenceRecord.inspection_id == inspection.id)
        .where(VisualEvidenceRecord.evidence_type == "DECLARATION_SYMBOL")
        .where(VisualEvidenceRecord.verification_status == "AUTOMATED")
        .where(VisualEvidenceRecord.value_text.in_(["vegetarian", "non_vegetarian"]))
        .order_by(VisualEvidenceRecord.confidence.desc())
    ).scalars().first()
    # Replace the composed row (if any) so re-analysis reflects the latest
    # evidence without touching AI-extracted rows.
    for old in session.execute(
        select(ExtractedField)
        .where(ExtractedField.inspection_id == inspection.id)
        .where(ExtractedField.field_name == "vegetarian_non_vegetarian")
    ).scalars():
        session.delete(old)
    if symbol is None:
        return False
    session.add(
        ExtractedField(
            inspection=inspection,
            field_name="vegetarian_non_vegetarian",
            status="detected",
            value_json={
                "declaration": symbol.value_text,
                "evidence_id": symbol.evidence_id,
                "bbox": symbol.bbox_json,
                "source": "visual-symbol-detection",
            },
            raw_text=None,  # no OCR text exists for a visual symbol
            ocr_confidence=None,
            # extraction_confidence is 0-100 elsewhere in this table; the CV
            # row's confidence is 0-1, so convert to the field's convention.
            extraction_confidence=round(float(symbol.confidence) * 100, 1)
            if symbol.confidence is not None
            else None,
            resolution_status=None,
            # Not "deterministic"/"ai_assisted": this value was measured, not read.
            method="visual",
        )
    )
    session.flush()
    return True


def get_visual_evidence(session: Session, inspection: Inspection) -> list[VisualEvidenceRecord]:
    """Persisted visual evidence for retrieval (empty list when none)."""
    return list(
        session.execute(
            select(VisualEvidenceRecord)
            .where(VisualEvidenceRecord.inspection_id == inspection.id)
            .order_by(VisualEvidenceRecord.id)
        ).scalars()
    )


def evidence_out(records: list[VisualEvidenceRecord]) -> list[dict]:
    """API shape for persisted evidence rows."""
    return [
        {
            "evidence_id": r.evidence_id,
            "evidence_type": r.evidence_type,
            "page_number": r.page_number,
            "bbox": r.bbox_json,
            "value": r.value_numeric if r.value_numeric is not None else r.value_text,
            "unit": r.unit,
            "confidence": float(r.confidence) if r.confidence is not None else None,
            "method": r.method,
            "verification_status": r.verification_status,
            "ocr_block_id": r.ocr_block_id,
            "ocr_block_ids": r.ocr_block_ids or [],
            "field_name": r.field_name,
            "note": r.note,
        }
        for r in records
    ]


def attach_to_evaluation_input(
    records: list[VisualEvidenceRecord],
    visual_evidence: dict,
) -> None:
    """Map persisted measurements onto the legal engine's visual_evidence.

    Only AUTOMATED physical values (calibration-produced cm2/mm) are mapped;
    pixel measurements are never converted, and measured_quantity is never
    set from image data — that field must come from a genuine measurement
    source, which the CV pipeline does not provide.
    """
    if not records:
        return
    visual_evidence["readability_measurements"] = [
        {
            "ocr_block_id": r.ocr_block_id,
            "laplacian_variance": float(r.value_numeric) if r.value_numeric is not None else None,
            "note": r.note,
            "confidence": float(r.confidence) if r.confidence is not None else None,
        }
        for r in records
        if r.evidence_type == "READABILITY" and r.verification_status == "AUTOMATED"
    ]
    visual_evidence["contrast_measurements"] = [
        {
            "ocr_block_id": r.ocr_block_id,
            "contrast": float(r.value_numeric) if r.value_numeric is not None else None,
            "method": r.method,
            "confidence": float(r.confidence) if r.confidence is not None else None,
        }
        for r in records
        if r.evidence_type == "CONTRAST" and r.verification_status == "AUTOMATED"
    ]
    declaration_regions = [
        {
            "category": r.value_text,
            "page_number": r.page_number,
            "bbox": r.bbox_json,
            "ocr_block_ids": r.ocr_block_ids or [],
            "field_name": r.field_name,
            "confidence": float(r.confidence) if r.confidence is not None else None,
        }
        for r in records
        if r.evidence_type == "DECLARATION_REGION" and r.verification_status == "AUTOMATED"
    ]
    if declaration_regions:
        visual_evidence["declaration_regions"] = declaration_regions
        visual_evidence["declaration_categories"] = sorted({r["category"] for r in declaration_regions})
    for r in records:
        if r.evidence_type != "PDP_AREA" or r.verification_status != "AUTOMATED":
            continue
        if r.unit == "px2" and r.bbox_json:
            # Candidate panel found — the engine learns of the panel itself.
            visual_evidence.setdefault("principal_display_panel_detected", True)
            visual_evidence.setdefault(
                "principal_display_panel_bbox_px", r.bbox_json
            )
        elif r.unit == "cm2" and r.value_numeric is not None:
            # Only a calibration-produced physical area may cross this line.
            visual_evidence["principal_display_panel_area_cm2"] = float(r.value_numeric)
    # NOTE: measured_quantity is deliberately never populated here.
