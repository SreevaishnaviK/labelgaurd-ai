"""Field merger: deterministic results + AI interpretation → final fields.

Policy (Phase 4):
1. High-confidence deterministic results remain authoritative for extraction.
2. AI may resolve ambiguity or supply values the rules missed — but only
   with valid OCR evidence (the orchestrator validates block IDs upstream).
3. AI never overrides strong deterministic evidence silently: disagreement
   becomes an explicit ambiguity with BOTH candidates preserved, methods
   attached, for later review.
4. Provenance is preserved on every field: method + resolution_status.

resolution_status values:
- "ai_resolved": AI supplied or selected the value.
- "ai_confirmed": AI agreed with the deterministic value.
- "conflict": deterministic and AI disagree (or AI added a new candidate) —
  stays ambiguous, never silently resolved.
- "ai_unavailable": AI was engaged but failed; deterministic result kept
  and marked deterministic_fallback.
Fields settled by rules alone carry None (no AI was involved).
"""
import re

from app.extraction import normalization as norm
from app.schemas.extraction import (
    AIFieldOut,
    EvidenceRef,
    ExtractedFieldOut,
    FieldCandidate,
)

# Canonical value shape for a plain-string AI value, per field.
_STR_SHAPE = {
    "product_name": "name",
    "manufacturer": "name",
    "packer": "name",
    "importer": "name",
    "marketer": "name",
    "manufacturer_address": "address",
    "packer_address": "address",
    "importer_address": "address",
    "manufacturing_date": "date",
    "packing_date": "date",
    "best_before": "date",
    "use_by": "date",
    "expiry_date": "date",
    "consumer_care": "contact",
    "customer_care_phone": "phone",
    "customer_care_email": "email",
    "website": "url",
    "batch_number": "batch",
    "lot_number": "lot",
    "country_of_origin": "country",
    "ingredients": "ingredients",
    "vegetarian_non_vegetarian": "declaration",
}

_MRP_VALUE_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)")
_NET_VALUE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(mg|g|gm|gms|kgs?|ml|l|ltr|litres?|liters?)\b", re.IGNORECASE)


def _coerce(field_name: str, value: object) -> dict | None:
    """Normalize an AI value into the deterministic value shape.

    Dicts pass through; strings are wrapped per field (the prompt shows the
    shapes via deterministic candidates, but non-compliant output must still
    merge honestly). Unusable types (bare numbers, ...) return None — the
    value can still appear as a raw_text-only candidate.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        key = _STR_SHAPE.get(field_name)
        if key:
            return {key: text}
        if field_name == "mrp":
            match = _MRP_VALUE_RE.search(text)
            if match:
                return {"amount": float(match.group(1).replace(",", "")), "currency": "INR"}
        if field_name == "net_quantity":
            match = _NET_VALUE_RE.search(text)
            if match:
                normalized = norm.normalize_mass(float(match.group(1)), match.group(2)) or norm.normalize_volume(
                    float(match.group(1)), match.group(2)
                )
                if normalized:
                    return {"value": normalized[0], "unit": normalized[1]}
        return {"value": text}
    return None


def _ref(block_id: str, block_page: dict[str, int]) -> EvidenceRef:
    return EvidenceRef(ocr_block_id=block_id, page_number=block_page.get(block_id, 1))


def _ai_evidence(ai: AIFieldOut, block_page: dict[str, int]) -> list[EvidenceRef]:
    return [_ref(b, block_page) for b in ai.evidence_block_ids]


def merge(
    det_fields: list[ExtractedFieldOut],
    ai_fields: list[AIFieldOut],
    *,
    block_page: dict[str, int],
    gated_fields: set[str],
    ai_failed: bool,
) -> list[ExtractedFieldOut]:
    """Merge deterministic fields with validated AI fields.

    gated_fields: names the orchestrator would have sent to AI (used only on
    the failure path to mark deterministic_fallback precisely).
    """
    ai_by_name = {f.field_name: f for f in ai_fields}
    return [
        _merge_one(det, ai_by_name.get(det.field_name),
                   block_page=block_page, gated=det.field_name in gated_fields, ai_failed=ai_failed)
        for det in det_fields
    ]


def _merge_one(
    det: ExtractedFieldOut,
    ai: AIFieldOut | None,
    *,
    block_page: dict[str, int],
    gated: bool,
    ai_failed: bool,
) -> ExtractedFieldOut:
    if ai_failed and gated:
        # AI was engaged for this field and failed: the deterministic result
        # stands, explicitly marked so provenance is never misleading.
        return det.model_copy(update={"method": "deterministic_fallback", "resolution_status": "ai_unavailable"})
    if ai is None or ai.status == "not_detected":
        # No AI reading (or a bare denial) never erases deterministic evidence.
        return det
    if det.status == "not_detected":
        return _adopt_ai(det, ai, block_page)
    if det.status == "ambiguous":
        return _resolve_ambiguity(det, ai, block_page)
    return _merge_detected(det, ai, block_page)


def _adopt_ai(det: ExtractedFieldOut, ai: AIFieldOut, block_page: dict[str, int]) -> ExtractedFieldOut:
    """Rules found nothing; AI found something with valid evidence."""
    value = _coerce(det.field_name, ai.value)
    evidence = _ai_evidence(ai, block_page)
    if ai.status == "ambiguous" or value is None:
        candidate = FieldCandidate(
            raw_text=ai.raw_text, value=value, method="ai_assisted",
            confidence=ai.confidence, evidence=evidence,
        )
        return det.model_copy(update={
            "status": "ambiguous", "value": None, "raw_text": ai.raw_text,
            "ai_confidence": ai.confidence,
            "method": "ai_assisted", "resolution_status": "ai_resolved",
            "evidence": evidence, "candidates": [candidate],
        })
    return det.model_copy(update={
        "status": "detected", "value": value, "raw_text": ai.raw_text,
        "ocr_confidence": None,  # enriched from evidence blocks by the orchestrator
        "extraction_confidence": ai.confidence, "ai_confidence": ai.confidence,
        "method": "ai_assisted", "resolution_status": "ai_resolved",
        "evidence": evidence, "candidates": None,
    })


def _resolve_ambiguity(det: ExtractedFieldOut, ai: AIFieldOut, block_page: dict[str, int]) -> ExtractedFieldOut:
    """Deterministic was ambiguous; AI may pick a candidate or add a new one."""
    det_candidates = list(det.candidates or [])
    ai_value = _coerce(det.field_name, ai.value)
    if ai.status == "detected" and ai_value is not None:
        for candidate in det_candidates:
            if candidate.value == ai_value:
                # AI resolved to an existing candidate: adopt it, keep the
                # full candidate list for audit (never discard readings).
                return det.model_copy(update={
                    "status": "detected", "value": ai_value,
                    "raw_text": ai.raw_text or candidate.raw_text,
                    "extraction_confidence": ai.confidence, "ai_confidence": ai.confidence,
                    "method": "ai_assisted", "resolution_status": "ai_resolved",
                    "evidence": _ai_evidence(ai, block_page),
                    "candidates": det_candidates,
                })
        # A third reading: keep everything ambiguous, add the AI candidate.
        return det.model_copy(update={
            "status": "ambiguous", "resolution_status": "conflict",
            "ai_confidence": ai.confidence,
            "candidates": [*det_candidates, FieldCandidate(
                raw_text=ai.raw_text, value=ai_value, method="ai_assisted",
                confidence=ai.confidence, evidence=_ai_evidence(ai, block_page),
            )],
        })
    # AI stayed ambiguous or returned an unusable value: deterministic
    # ambiguity stands unchanged.
    return det


def _merge_detected(det: ExtractedFieldOut, ai: AIFieldOut, block_page: dict[str, int]) -> ExtractedFieldOut:
    ai_value = _coerce(det.field_name, ai.value)
    if ai_value is not None and ai_value == det.value:
        return det.model_copy(update={"resolution_status": "ai_confirmed", "ai_confidence": ai.confidence})
    # Disagreement: surface BOTH candidates as ambiguous — never silently
    # select the AI value over deterministic evidence (or vice versa).
    return det.model_copy(update={
        "status": "ambiguous", "value": None,
        "resolution_status": "conflict", "ai_confidence": ai.confidence,
        "candidates": [
            FieldCandidate(
                raw_text=det.raw_text, value=det.value, method="deterministic",
                confidence=det.extraction_confidence, evidence=list(det.evidence),
            ),
            FieldCandidate(
                raw_text=ai.raw_text, value=ai_value, method="ai_assisted",
                confidence=ai.confidence, evidence=_ai_evidence(ai, block_page),
            ),
        ],
    })
