"""Officer verification service (Phase 8).

Officer decisions are a separate layer over immutable automated results:
RuleEvaluation rows are never modified, verifications append new rows
(history preserved), the latest per rule is the effective decision, and
every action writes an append-only audit record. Effective status is
calculated here — never in React.
"""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.inspection import (
    AuditLog,
    ExtractedField,
    FieldVerification,
    Inspection,
    InspectionEvaluation,
    OfficerDecision,
    OfficerVerification,
    RuleEvaluation,
)

logger = logging.getLogger(__name__)

# Development-only officer identity. Authentication and role-based access
# control are deferred to a later phase — this identifier is NOT secure
# authentication and must not be presented as such.
DEVELOPMENT_OFFICER_ID = "officer-dev"


def _fail(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def officer_identifier() -> str:
    """Development placeholder identity — replaced by real auth later."""
    return get_settings().officer_identifier or DEVELOPMENT_OFFICER_ID


def _get_verified(
    session: Session,
    inspection: Inspection,
    rule_evaluation_id: int,
) -> tuple[InspectionEvaluation, RuleEvaluation]:
    """Load a rule evaluation, enforcing the full ownership chain.

    Inspection A must never reach a rule evaluation from inspection B.
    """
    rule = session.get(RuleEvaluation, rule_evaluation_id)
    if rule is None:
        raise _fail(404, "RULE_EVALUATION_NOT_FOUND", "No such rule evaluation.")
    evaluation = session.get(InspectionEvaluation, rule.inspection_evaluation_id)
    if evaluation is None or evaluation.inspection_id != inspection.id:
        raise _fail(
            409,
            "EVALUATION_MISMATCH",
            "Rule evaluation does not belong to this inspection.",
        )
    return evaluation, rule


def _validate_decision(decision: OfficerDecision, rule: RuleEvaluation) -> None:
    """A CONFIRM_* decision must agree with the automated status it confirms."""
    confirmed = {
        OfficerDecision.CONFIRM_REVIEW_REQUIRED: "REVIEW_REQUIRED",
        OfficerDecision.CONFIRM_NOT_VERIFIABLE: "NOT_VERIFIABLE",
        OfficerDecision.CONFIRM_NOT_APPLICABLE: "NOT_APPLICABLE",
    }
    if decision in confirmed and confirmed[decision] != rule.status:
        raise _fail(
            409,
            "DECISION_CONFLICT",
            f"Cannot confirm {confirmed[decision]} for a rule with automated status {rule.status}.",
        )


def create_verification(
    session: Session,
    inspection: Inspection,
    rule_evaluation_id: int,
    decision: OfficerDecision,
    comment: str | None,
    evidence_ocr_block_id: str | None = None,
    evidence_visual_evidence_id: str | None = None,
    evidence_extracted_field_id: int | None = None,
) -> OfficerVerification:
    """Append a verification row + audit entry; the rule evaluation is untouched."""
    evaluation, rule = _get_verified(session, inspection, rule_evaluation_id)
    _validate_decision(decision, rule)

    if decision in (OfficerDecision.OVERRIDE_COMPLIANT, OfficerDecision.OVERRIDE_VIOLATION):
        if not comment or not comment.strip():
            raise _fail(422, "COMMENT_REQUIRED", "An override requires a written reason.")
    if comment and len(comment) > 4000:
        raise _fail(422, "COMMENT_TOO_LONG", "Comment exceeds 4000 characters.")

    _validate_evidence(
        session,
        inspection,
        evidence_ocr_block_id,
        evidence_visual_evidence_id,
        evidence_extracted_field_id,
    )

    previous = latest_for_rule(session, rule.id)
    verification = OfficerVerification(
        inspection_id=inspection.id,
        inspection_evaluation_id=evaluation.id,
        rule_evaluation_id=rule.id,
        officer_identifier=officer_identifier(),
        decision=decision,
        comment=comment.strip() if comment else None,
        evidence_ocr_block_id=evidence_ocr_block_id,
        evidence_visual_evidence_id=evidence_visual_evidence_id,
        evidence_extracted_field_id=evidence_extracted_field_id,
    )
    session.add(verification)
    session.flush()
    session.add(
        AuditLog(
            inspection_id=inspection.id,
            actor=officer_identifier(),
            action="RULE_VERIFICATION",
            evaluation_id=evaluation.id,
            rule_evaluation_id=rule.id,
            decision=decision.value,
            previous_state=effective_status_for(previous, rule),
            comment=verification.comment,
        )
    )
    return verification


def _validate_evidence(
    session: Session,
    inspection: Inspection,
    ocr_block_id: str | None,
    visual_evidence_id: str | None,
    extracted_field_id: int | None,
) -> None:
    """Every supplied evidence reference must exist within this inspection."""
    if ocr_block_id is not None:
        from app.models.inspection import OCRBlock

        exists = session.execute(
            select(OCRBlock.id).where(
                OCRBlock.inspection_id == inspection.id, OCRBlock.block_id == ocr_block_id
            )
        ).first()
        if not exists:
            raise _fail(409, "EVIDENCE_NOT_FOUND", f"OCR block {ocr_block_id} is not part of this inspection.")
    if visual_evidence_id is not None:
        from app.models.inspection import VisualEvidenceRecord

        exists = session.execute(
            select(VisualEvidenceRecord.id).where(
                VisualEvidenceRecord.inspection_id == inspection.id,
                VisualEvidenceRecord.evidence_id == visual_evidence_id,
            )
        ).first()
        if not exists:
            raise _fail(409, "EVIDENCE_NOT_FOUND", f"Visual evidence {visual_evidence_id} is not part of this inspection.")
    if extracted_field_id is not None:
        field = session.get(ExtractedField, extracted_field_id)
        if field is None or field.inspection_id != inspection.id:
            raise _fail(409, "EVIDENCE_NOT_FOUND", "Extracted field does not belong to this inspection.")


def latest_for_rule(session: Session, rule_evaluation_id: int) -> OfficerVerification | None:
    return (
        session.execute(
            select(OfficerVerification)
            .where(OfficerVerification.rule_evaluation_id == rule_evaluation_id)
            .order_by(OfficerVerification.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def effective_status_for(verification: OfficerVerification | None, rule: RuleEvaluation) -> str:
    """Backend-derived: officer decision when present, automated otherwise."""
    if verification is None:
        return rule.status
    if verification.decision is OfficerDecision.OVERRIDE_COMPLIANT:
        return "COMPLIANT"
    if verification.decision is OfficerDecision.OVERRIDE_VIOLATION:
        return "VIOLATION"
    if verification.decision is OfficerDecision.ACCEPT:
        return rule.status
    if verification.decision is OfficerDecision.CONFIRM_REVIEW_REQUIRED:
        return "REVIEW_REQUIRED"
    if verification.decision is OfficerDecision.CONFIRM_NOT_VERIFIABLE:
        return "NOT_VERIFIABLE"
    return "NOT_APPLICABLE"


def latest_field_verification(session: Session, extracted_field_id: int) -> FieldVerification | None:
    return (
        session.execute(
            select(FieldVerification)
            .where(FieldVerification.extracted_field_id == extracted_field_id)
            .order_by(FieldVerification.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def create_field_verification(
    session: Session,
    inspection: Inspection,
    extracted_field_id: int,
    verification_status: str,
    verified_value: dict | None,
    comment: str | None,
    evidence_ocr_block_id: str | None = None,
    evidence_visual_evidence_id: str | None = None,
) -> FieldVerification:
    """Append a field verification + audit entry; the extracted field is untouched."""
    field = session.get(ExtractedField, extracted_field_id)
    if field is None or field.inspection_id != inspection.id:
        raise _fail(404, "FIELD_NOT_FOUND", "Extracted field does not belong to this inspection.")
    if verification_status not in ("verified", "corrected"):
        raise _fail(422, "INVALID_STATUS", "verification_status must be 'verified' or 'corrected'.")
    if verification_status == "corrected" and verified_value is None:
        raise _fail(422, "VALUE_REQUIRED", "A corrected field requires a verified value.")
    if comment and len(comment) > 4000:
        raise _fail(422, "COMMENT_TOO_LONG", "Comment exceeds 4000 characters.")
    _validate_evidence(session, inspection, evidence_ocr_block_id, evidence_visual_evidence_id, None)

    verification = FieldVerification(
        inspection_id=inspection.id,
        extracted_field_id=extracted_field_id,
        officer_identifier=officer_identifier(),
        verification_status=verification_status,
        verified_value=verified_value,
        comment=comment.strip() if comment else None,
        evidence_ocr_block_id=evidence_ocr_block_id,
        evidence_visual_evidence_id=evidence_visual_evidence_id,
    )
    session.add(verification)
    session.flush()
    session.add(
        AuditLog(
            inspection_id=inspection.id,
            actor=officer_identifier(),
            action="FIELD_VERIFICATION",
            decision=verification_status,
            previous_state=field.status,
            comment=verification.comment,
        )
    )
    return verification


def evaluation_effective(
    session: Session, evaluation: InspectionEvaluation, results: list[dict]
) -> str:
    """Inspection-level rollup: effective per-rule statuses, same rules as the
    automated overall_status(). Never a score, never a certification."""
    statuses = set()
    for result in results:
        rule = session.execute(
            select(RuleEvaluation).where(
                RuleEvaluation.inspection_evaluation_id == evaluation.id,
                RuleEvaluation.rule_id == result["rule_id"],
            )
        ).scalar_one()
        verification = latest_for_rule(session, rule.id)
        statuses.add(effective_status_for(verification, rule))
    if "VIOLATION" in statuses:
        return "NON_COMPLIANT"
    if "REVIEW_REQUIRED" in statuses:
        return "REVIEW_REQUIRED"
    if "NOT_VERIFIABLE" in statuses or "NOT_APPLICABLE" in statuses:
        return "INCOMPLETE"
    return "COMPLIANT"


def enrich_evaluation(session: Session, evaluation: InspectionEvaluation, payload: dict) -> dict:
    """Attach officer_verification + effective_status to an evaluation payload.

    The `automated` block stays exactly as the engine produced it; officer
    data is layered beside it. Verifications belong to a specific evaluation
    version — a newer evaluation shows "Not yet verified" until reviewed.
    """
    rules = {
        row.rule_id: row
        for row in (
            session.execute(
                select(RuleEvaluation)
                .where(RuleEvaluation.inspection_evaluation_id == evaluation.id)
                .options(selectinload(RuleEvaluation.evidence))
            )
            .scalars()
            .all()
        )
    }
    for result in payload["results"]:
        rule = rules.get(result["rule_id"])
        if rule is None:
            continue
        verification = latest_for_rule(session, rule.id)
        result["effective_status"] = effective_status_for(verification, rule)
        result["officer_verification"] = (
            {
                "id": verification.id,
                "decision": verification.decision.value,
                "comment": verification.comment,
                "officer_identifier": verification.officer_identifier,
                "verified_at": verification.created_at,
                "evidence_ocr_block_id": verification.evidence_ocr_block_id,
                "evidence_visual_evidence_id": verification.evidence_visual_evidence_id,
                "evidence_extracted_field_id": verification.evidence_extracted_field_id,
            }
            if verification
            else None
        )
    payload["officer_effective_status"] = evaluation_effective(session, evaluation, payload["results"])
    return payload


def verification_out(verification: OfficerVerification, session: Session) -> dict:
    return {
        "id": verification.id,
        "inspection_id": session.get(Inspection, verification.inspection_id).inspection_id,
        "evaluation_id": verification.inspection_evaluation_id,
        "rule_evaluation_id": verification.rule_evaluation_id,
        "decision": verification.decision.value,
        "comment": verification.comment,
        "officer_identifier": verification.officer_identifier,
        "evidence_ocr_block_id": verification.evidence_ocr_block_id,
        "evidence_visual_evidence_id": verification.evidence_visual_evidence_id,
        "evidence_extracted_field_id": verification.evidence_extracted_field_id,
        "created_at": verification.created_at,
    }


def field_verification_out(verification: FieldVerification, session: Session) -> dict:
    field = session.get(ExtractedField, verification.extracted_field_id)
    return {
        "id": verification.id,
        "extracted_field_id": verification.extracted_field_id,
        "field_name": field.field_name if field else "",
        "verification_status": verification.verification_status,
        "verified_value": verification.verified_value,
        "comment": verification.comment,
        "officer_identifier": verification.officer_identifier,
        "evidence_ocr_block_id": verification.evidence_ocr_block_id,
        "evidence_visual_evidence_id": verification.evidence_visual_evidence_id,
        "created_at": verification.created_at,
    }
