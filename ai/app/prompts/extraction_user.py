"""User prompt builder: OCR + deterministic candidates as compact JSON."""
import json

from app.schemas.extraction import CandidateField, ExtractRequest


def _candidate_payload(candidate: CandidateField) -> dict:
    payload = {
        "field_name": candidate.field_name,
        "status": candidate.status,
        "value": candidate.value,
        "extraction_confidence": candidate.extraction_confidence,
    }
    if candidate.readings:
        payload["readings"] = [
            {
                "value": r.value,
                "raw_text": r.raw_text,
                "confidence": r.confidence,
                "evidence": [e.ocr_block_id for e in r.evidence],
            }
            for r in candidate.readings
        ]
    return payload


def build_user_prompt(request: ExtractRequest, candidates: list[CandidateField]) -> str:
    """Everything the model may use — OCR evidence and deterministic candidates."""
    payload = {
        "inspection_id": request.inspection_id,
        "pages": [
            {
                "page_number": page.page_number,
                "full_text": page.full_text,
                "blocks": [
                    {
                        "id": b.id,
                        "text": b.text,
                        "confidence": b.confidence,
                        "page_number": b.page_number,
                        "bbox": b.bbox,
                    }
                    for b in page.blocks
                ],
            }
            for page in request.pages
        ],
        "deterministic_candidates": [_candidate_payload(c) for c in candidates],
    }
    return json.dumps(payload, ensure_ascii=False)
