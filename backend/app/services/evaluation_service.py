"""Compliance evaluation service (Phase 6).

Builds the Legal Engine's evaluation input from persisted inspection data —
only detected fields with real evidence are mapped; nothing is invented
(visual evidence stays empty, label_fully_processed stays unset, package
flags stay at their defaults). Results are persisted as an immutable new
evaluation row: re-evaluation appends a version, never mutates history.

Evidence traceability: every mapped field's OCR block references ride along
into the persisted evidence table so each rule result can be traced back to
the exact blocks that support it.
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.clients import legal_engine_client
from app.clients.legal_engine_client import LegalEngineError
from app.config import get_settings
from app.models.inspection import (
    ExtractedField,
    Inspection,
    InspectionEvaluation,
    RuleEvaluation,
    RuleEvaluationEvidence,
    VisualEvidenceRecord,
)
from app.services import evidence_service

logger = logging.getLogger(__name__)


class ExtractionUnavailableError(LegalEngineError):
    """The inspection has no persisted extraction to evaluate."""

# Value shapes produced by the AI service's extraction (single source of
# truth: ai/app/extraction). Keys inside value_json per field.
_TEXT_KEYS = {
    "product_name": ("name",),
    "manufacturer": ("name",),
    "packer": ("name",),
    "importer": ("name",),
    "marketer": ("name",),
    "manufacturer_address": ("address",),
    "packer_address": ("address",),
    "importer_address": ("address",),
    "manufacturing_date": ("date",),
    "packing_date": ("date",),
    "best_before": ("date",),
    "use_by": ("date",),
    "expiry_date": ("date",),
    "consumer_care": ("contact",),
    "customer_care_phone": ("phone",),
    "customer_care_email": ("email",),
    "website": ("url",),
    "batch_number": ("batch", "lot"),
    "lot_number": ("batch", "lot"),
    "country_of_origin": ("country",),
    "ingredients": ("ingredients",),
    "vegetarian_non_vegetarian": ("declaration",),
}


def _text_of(field: ExtractedField) -> str | None:
    """First non-empty string in the field's value dict, per its known shape."""
    value = field.value_json or {}
    for key in _TEXT_KEYS.get(field.field_name, ()):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    # Unknown shape: fall back to any non-empty string value (never a guess).
    for text in value.values():
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _net_quantity(field: ExtractedField) -> tuple[float, str] | None:
    value = field.value_json or {}
    amount, unit = value.get("value"), value.get("unit")
    if isinstance(amount, (int, float)) and isinstance(unit, str) and unit.strip():
        return float(amount), unit.strip().lower()
    return None


def _mrp(field: ExtractedField) -> tuple[float, str] | None:
    value = field.value_json or {}
    amount, currency = value.get("amount"), value.get("currency")
    if isinstance(amount, (int, float)) and isinstance(currency, str) and currency.strip():
        return float(amount), currency.strip().upper()
    return None


def build_evaluation_input(
    inspection: Inspection, fields: list[ExtractedField]
) -> tuple[dict, dict[str, ExtractedField], dict[str, str]]:
    """Legal Engine input, mapped fields by name, and product-key provenance.

    The third map records which extracted field fed each product key — the
    evidence trail is built from it, so every rule result traces back to the
    fields (and through them, OCR blocks) that actually supplied its data.

    Package facts stay at defaults: nothing in the pipeline establishes
    import/wholesale/food status yet, so asserting them would invent
    evidence. Visual evidence stays empty for the same reason.
    """
    by_name: dict[str, ExtractedField] = {}
    key_to_field: dict[str, str] = {}
    product: dict = {}
    for field in fields:
        if field.status != "detected":
            continue  # ambiguous/not_detected never contribute a value
        name = field.field_name
        if name in ("net_quantity",):
            parsed = _net_quantity(field)
            if parsed:
                product["net_quantity"], product["quantity_unit"] = parsed
                by_name[name] = field
                key_to_field["net_quantity"] = name
                key_to_field["quantity_unit"] = name
        elif name == "mrp":
            parsed = _mrp(field)
            if parsed:
                product["mrp"] = {"amount": parsed[0], "currency": parsed[1]}
                by_name[name] = field
                key_to_field["mrp"] = name
        else:
            text = _text_of(field)
            if text:
                product[name] = text
                by_name[name] = field
                key_to_field[name] = name
    # A strict MM/YYYY (or MM-YYYY) manufacturing date is mechanical
    # normalization into the month/year fields the engine's Rule 6 check
    # reads; any other format stays an unmapped raw string (never guessed).
    raw_date = product.get("manufacturing_date")
    if raw_date and "manufacture_month" not in product:
        import re

        match = re.fullmatch(r"(\d{1,2})[/\-](\d{4})", raw_date.strip())
        if match:
            product["manufacture_month"] = int(match.group(1))
            product["manufacture_year"] = int(match.group(2))
            key_to_field["manufacture_month"] = "manufacturing_date"
            key_to_field["manufacture_year"] = "manufacturing_date"
    # Addresses are declared per-party; a generic address never impersonates
    # a party-specific one.
    product.pop("address", None)
    return (
        {
            "product": product,
            "package": {},  # defaults: retail-only, no invented facts
            "visual_evidence": {"evidence_block_ids": []},
        },
        by_name,
        key_to_field,
    )


def _evidence_rows(field: ExtractedField, field_id_map: dict[str, int]) -> list[dict]:
    """Persisted evidence references for one mapped field."""
    rows = [
        {
            "evidence_type": "extracted_field",
            "evidence_reference": field.field_name,
            "extracted_field_id": field_id_map[field.field_name],
        }
    ]
    for ref in field.evidence:
        rows.append(
            {
                "evidence_type": "ocr_block",
                "evidence_reference": ref.ocr_block_id,
                "ocr_block_id": ref.ocr_block_id,
                "page_number": ref.page_number,
            }
        )
    return rows


def _latest_version(session: Session, inspection_pk: int) -> int:
    return (
        session.execute(
            select(func.max(InspectionEvaluation.evaluation_version)).where(
                InspectionEvaluation.inspection_id == inspection_pk
            )
        ).scalar()
        or 0
    )


def overall_status(results: list[dict]) -> str:
    """Rollup without a score and without legal certification language.

    NON_COMPLIANT only when a rule's evidence established a violation;
    REVIEW_REQUIRED when something needs human judgment; INCOMPLETE when the
    engine could not verify (e.g. unmeasured letter heights); COMPLIANT only
    when everything applicable was affirmatively satisfied.
    """
    statuses = {r["status"] for r in results}
    if "VIOLATION" in statuses:
        return "NON_COMPLIANT"
    if "REVIEW_REQUIRED" in statuses:
        return "REVIEW_REQUIRED"
    if "NOT_VERIFIABLE" in statuses or "NOT_APPLICABLE" in statuses:
        return "INCOMPLETE"
    return "COMPLIANT"


def _attach_visual_evidence(
    results: list[dict],
    visual_records: list[VisualEvidenceRecord],
) -> None:
    """Give Rule 9's contrast result its supporting measurement as evidence."""
    measurements = [
        r for r in visual_records if r.evidence_type == "CONTRAST" and r.ocr_block_id
    ]
    if not measurements:
        return
    for result in results:
        if result.get("rule_id") == "LMPC-R9-A":
            result["evidence"] = list(result.get("evidence") or []) + [
                {
                    "field_name": "contrast_measurement",
                    "ocr_block_ids": [r.ocr_block_id for r in measurements],
                    "extraction_confidence": None,
                }
            ]


def _parse_confidence(raw: object) -> float | None:
    """Legal engine confidences arrive as 0-100 or 0-1; store 0-1 or None."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if 0 <= value <= 1:
        return round(value, 3)
    if 0 < value <= 100:
        return round(value / 100, 3)
    return None


def _persist(
    session: Session,
    inspection: Inspection,
    engine_version: str,
    results: list[dict],
    field_id_map: dict[str, int],
    field_map: dict[str, ExtractedField],
) -> InspectionEvaluation:
    evaluation = InspectionEvaluation(
        inspection=inspection,
        evaluation_version=_latest_version(session, inspection.id) + 1,
        engine_version=engine_version,
        overall_status=overall_status(results),
    )
    session.add(evaluation)
    session.flush()
    for result in results:
        rule_row = RuleEvaluation(
            evaluation=evaluation,
            rule_id=result["rule_id"],
            rule_number=result["rule_number"],
            rule_title=result["title"],
            status=result["status"],
            severity=result["severity"],
            finding=result["finding"],
            required_information=result.get("required_information") or [],
            actual_information=result.get("actual_information") or {},
            confidence=_parse_confidence(result.get("confidence")),
            requires_officer_verification=bool(result.get("requires_officer_verification")),
            source=result.get("source") or {},
        )
        session.add(rule_row)
        session.flush()
        seen: set[tuple] = set()
        for ref in result.get("evidence") or []:
            if not isinstance(ref, dict):
                continue
            rows: list[dict] = []
            name = ref.get("field_name")
            if name and name in field_id_map:
                rows = _evidence_rows(field_map[name], field_id_map)
            elif ref.get("ocr_block_ids"):
                # Visual-measurement provenance: raw block references without
                # an owning extracted field (e.g. contrast measurements).
                for block_id in ref["ocr_block_ids"]:
                    rows.append(
                        {
                            "evidence_type": "ocr_block",
                            "evidence_reference": str(block_id),
                            "ocr_block_id": str(block_id),
                            "page_number": ref.get("page_number"),
                        }
                    )
            elif ref.get("ocr_block_id"):
                block_id = str(ref["ocr_block_id"])
                rows = [
                    {
                        "evidence_type": "ocr_block",
                        "evidence_reference": block_id,
                        "ocr_block_id": block_id,
                        "page_number": ref.get("page_number"),
                    }
                ]
            for row in rows:
                key = (row["evidence_type"], row.get("ocr_block_id"), row.get("extracted_field_id"))
                if key in seen:
                    continue
                seen.add(key)
                session.add(RuleEvaluationEvidence(rule_evaluation=rule_row, **row))
    return evaluation


def _block_ids_for_field(field: ExtractedField) -> list[str]:
    return [ref.ocr_block_id for ref in field.evidence]


def _attach_field_evidence(
    results: list[dict],
    field_map: dict[str, ExtractedField],
    key_to_field: dict[str, str],
) -> None:
    """Attach extracted-field/OCR-block evidence to results that used them.

    The engine's required_information names the product keys each rule reads;
    the provenance map turns those keys back into the extracted fields (and
    their OCR blocks) that supplied them. Evidence is attached only to rules
    that actually consumed a field — never speculatively.
    """
    for result in results:
        fields_used = {
            key_to_field[key]
            for key in result.get("required_information") or []
            if key in key_to_field
        }
        linked: list[dict] = list(result.get("evidence") or [])
        for name in sorted(fields_used):
            field = field_map[name]
            if any(isinstance(e, dict) and e.get("field_name") == name for e in linked):
                continue
            linked.append(
                {
                    "field_name": name,
                    "ocr_block_ids": _block_ids_for_field(field),
                    "extraction_confidence": (
                        float(field.extraction_confidence)
                        if field.extraction_confidence is not None
                        else None
                    ),
                }
            )
        result["evidence"] = linked


def evaluate_inspection(session: Session, inspection: Inspection) -> InspectionEvaluation:
    """Run the full evaluation flow; raises LegalEngineError on engine failure."""
    fields = (
        session.execute(
            select(ExtractedField)
            .where(ExtractedField.inspection_id == inspection.id)
            .options(selectinload(ExtractedField.evidence))
            .order_by(ExtractedField.id)
        )
        .scalars()
        .all()
    )
    if not fields:
        raise ExtractionUnavailableError("No extraction available for this inspection.")

    payload, field_map, key_to_field = build_evaluation_input(inspection, fields)
    # Phase 7: persisted visual measurements join the input — only calibrated
    # physical values and objective metrics; never invented, never pixels-as-mm.
    visual_records = evidence_service.get_visual_evidence(session, inspection)
    evidence_service.attach_to_evaluation_input(visual_records, payload["visual_evidence"])
    try:
        engine = legal_engine_client.evaluate(payload)
    except LegalEngineError:
        raise
    results = engine.results
    _attach_field_evidence(results, field_map, key_to_field)
    _attach_visual_evidence(results, visual_records)

    # Persisted field ids for evidence rows.
    field_id_map = {field.field_name: field.id for field in fields}
    evaluation = _persist(session, inspection, engine_version=_engine_version(), results=results,
                          field_id_map=field_id_map, field_map=field_map)
    session.commit()
    return evaluation


def _engine_version() -> str:
    """The legal engine's version from its health endpoint (cached per run)."""
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.legal_engine_url}/health", timeout=5)
        version = response.json().get("version")
        if isinstance(version, str) and version:
            return version
    except (httpx.HTTPError, ValueError):
        pass
    return "unknown"


def latest_evaluation(session: Session, inspection: Inspection) -> InspectionEvaluation | None:
    """Highest-version evaluation for an inspection, if any."""
    return (
        session.execute(
            select(InspectionEvaluation)
            .where(InspectionEvaluation.inspection_id == inspection.id)
            .order_by(InspectionEvaluation.evaluation_version.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def evaluation_out(evaluation: InspectionEvaluation) -> dict:
    """API shape for one persisted evaluation (with rule results + evidence)."""
    return {
        "evaluation_id": evaluation.id,
        "evaluation_version": evaluation.evaluation_version,
        "engine_version": evaluation.engine_version,
        "overall_status": evaluation.overall_status,
        "evaluated_at": evaluation.created_at,
        "results": [
            {
                "rule_evaluation_id": row.id,
                "rule_id": row.rule_id,
                "rule_number": row.rule_number,
                "rule_title": row.rule_title,
                "status": row.status,
                "severity": row.severity,
                "finding": row.finding,
                "required_information": row.required_information or [],
                "actual_information": row.actual_information or {},
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "requires_officer_verification": row.requires_officer_verification,
                "source": row.source or {},
                "evidence": [
                    {
                        "evidence_type": ref.evidence_type,
                        "evidence_reference": ref.evidence_reference,
                        "ocr_block_id": ref.ocr_block_id,
                        "page_number": ref.page_number,
                        "extracted_field_id": ref.extracted_field_id,
                        "source_page": ref.source_page,
                    }
                    for ref in row.evidence
                ],
            }
            for row in sorted(
                evaluation.rule_results, key=lambda r: (r.rule_number, r.rule_id)
            )
        ],
    }
