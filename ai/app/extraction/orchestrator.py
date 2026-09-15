"""Extraction orchestration: deterministic first, AI only where useful.

Modes (POST /api/v1/extract "mode"):
- "deterministic": rules only; a configured provider is never consulted.
- "ai_assisted": the provider reviews every field (when one is configured).
- "auto" (default): the provider is consulted only when the deterministic
  pass leaves ambiguity or weakly-supported values — never for a clean,
  confident read (cost safety: at most one provider call per extraction).

Provider selection is environmental (AI_PROVIDER=none|mock|openai); with no
provider the deterministic result is final — AI being OFF is a valid mode,
not a failure, so nothing is marked fallback.

Every AI response is re-validated here before merging: known field names,
schema-validated payload, and evidence block IDs that exist in the supplied
OCR. The prompt is defense in depth, not the only guard against
hallucination. Provider failures degrade to deterministic_fallback on the
gated fields and never fail the request.
"""
import logging

from app.config import get_settings
from app.extraction.base import FIELD_NAMES
from app.extraction.candidates import build_candidates
from app.extraction.extractor import get_field_extractor
from app.extraction.merger import merge
from app.providers import get_ai_provider
from app.providers.base import AIProviderError
from app.schemas.extraction import (
    AIExtractionOut,
    AIFieldOut,
    ExtractRequest,
    ExtractSuccess,
    ExtractedFieldOut,
)

logger = logging.getLogger(__name__)


def _gated_fields(fields: list[ExtractedFieldOut], threshold: float) -> set[str]:
    """Fields AI may improve: ambiguous, or extracted below the confidence
    threshold. not_detected fields are deliberately NOT gated — gating on
    them would call the provider on virtually every label (real labels leave
    most of the 24 fields undetected). When a call does happen the model
    still sees the full OCR and can report missed fields."""
    return {
        f.field_name
        for f in fields
        if f.status == "ambiguous"
        or (f.extraction_confidence is not None and f.extraction_confidence < threshold)
    }


def _validate_ai_fields(ai_out: AIExtractionOut, valid_block_ids: set[str]) -> list[AIFieldOut]:
    """Reject hallucinated fields and evidence-free readings, keep the rest."""
    kept: list[AIFieldOut] = []
    for field in ai_out.fields:
        if field.status == "not_detected":
            kept.append(field)
            continue
        if field.field_name not in FIELD_NAMES:
            logger.warning("Rejected AI field %r: unknown field name.", field.field_name)
            continue
        if not field.evidence_block_ids or any(b not in valid_block_ids for b in field.evidence_block_ids):
            logger.warning("Rejected AI field %r: missing or unknown OCR evidence blocks.", field.field_name)
            continue
        kept.append(field)
    return kept


def _enrich_ocr_confidence(
    fields: list[ExtractedFieldOut], block_confidence: dict[str, float]
) -> list[ExtractedFieldOut]:
    """AI-adopted fields get real OCR confidence from their evidence blocks."""
    for field in fields:
        if field.method == "ai_assisted" and field.ocr_confidence is None and field.evidence:
            values = [
                block_confidence[e.ocr_block_id]
                for e in field.evidence
                if e.ocr_block_id in block_confidence
            ]
            if values:
                field.ocr_confidence = round(sum(values) / len(values), 1)
    return fields


def run_extraction(request: ExtractRequest) -> ExtractSuccess:
    settings = get_settings()
    det_fields = get_field_extractor().extract_fields(request.pages)
    mode = request.mode
    fields = det_fields
    provider_name = "none"
    block_page = {b.id: b.page_number for page in request.pages for b in page.blocks}
    block_confidence = {b.id: b.confidence for page in request.pages for b in page.blocks}

    if mode != "deterministic":
        gated: set[str] = set()
        try:
            provider = get_ai_provider()
            if provider is None:
                gated = set()
            else:
                provider_name = provider.name
                if mode == "ai_assisted":
                    gated = {f.field_name for f in det_fields}
                else:
                    gated = _gated_fields(det_fields, settings.ai_min_deterministic_confidence)
                if not gated:
                    # Configured but never needed: nothing was sent to AI.
                    logger.info("AI provider configured but gating found nothing to consult.")
                else:
                    ai_out = provider.extract_fields(request, build_candidates(det_fields))
                    ai_fields = _validate_ai_fields(ai_out, set(block_page))
                    fields = merge(
                        det_fields, ai_fields,
                        block_page=block_page, gated_fields=gated, ai_failed=False,
                    )
        except AIProviderError as exc:
            # Construction, transport, and payload failures all degrade here.
            logger.warning("AI provider failed; deterministic result kept: %s", exc)
            fields = merge(
                det_fields, [],
                block_page=block_page, gated_fields=gated, ai_failed=True,
            )
        except Exception as exc:  # noqa: BLE001 - a provider bug must never
            # destroy the inspection (Phase 4 fallback rule).
            logger.warning("AI provider raised unexpectedly; deterministic result kept: %s", exc, exc_info=exc)
            fields = merge(
                det_fields, [],
                block_page=block_page, gated_fields=gated, ai_failed=True,
            )

    return ExtractSuccess(
        status="success",
        inspection_id=request.inspection_id,
        provider=provider_name,
        mode=mode,
        fields=_enrich_ocr_confidence(fields, block_confidence),
    )
