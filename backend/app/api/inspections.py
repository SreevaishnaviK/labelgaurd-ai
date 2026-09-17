"""Inspection API routes (Phase 2 upload/retrieval, Phase 6 evaluation,
Phase 7 evidence, Phase 8 officer verification, Phase 9 history/reports)."""
import mimetypes
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inspection import AuditLog, FieldVerification, OfficerDecision, OfficerVerification
from app.schemas.inspection import (
    AuditLogOut,
    DashboardMetricsOut,
    EvaluationOut,
    EvaluationVersionOut,
    ExtractionEvidenceOut,
    ExtractionOut,
    ExtractedFieldOut,
    FieldCandidateOut,
    FieldVerificationIn,
    FieldVerificationOut,
    InspectionHistoryOut,
    InspectionOut,
    OCRBlockOut,
    OCRPageOut,
    OfficerVerificationIn,
    OfficerVerificationOut,
    ReportOut,
    UploadSuccess,
    VisualEvidenceOut,
)
from app.services import evaluation_service, evidence_service, history_service, inspection_service, report_service, verification_service
from app.services.evaluation_service import latest_evaluation
from app.services.inspection_service import average_confidence, get_extracted_fields
from app.config import get_settings

router = APIRouter(prefix="/api/v1/inspections")


@router.post("/upload", response_model=UploadSuccess)
def upload_inspection(file: UploadFile = File(...), session: Session = Depends(get_db)) -> UploadSuccess:
    inspection = inspection_service.create_inspection_from_upload(file, session)
    full_text = "\n\n".join(doc.full_text or "" for doc in inspection.ocr_documents)
    return UploadSuccess(
        inspection_id=inspection.inspection_id,
        status=inspection.processing_status.value,
        filename=inspection.original_filename or "",
        document_type=inspection.document_type or "image",
        pages=inspection.page_count or 0,
        text_length=len(full_text),
        blocks_detected=len(inspection.ocr_blocks),
    )


def _to_out(inspection, session: Session) -> InspectionOut:
    pages = [
        OCRPageOut(
            page_number=doc.page_number,
            width=doc.width,
            height=doc.height,
            full_text=doc.full_text or "",
            processed_path=doc.processed_path,
            warped=bool(doc.warped),
        )
        for doc in sorted(inspection.ocr_documents, key=lambda d: d.page_number)
    ]
    blocks = [
        OCRBlockOut(
            block_id=block.block_id,
            page_number=block.page_number,
            text=block.text,
            confidence=float(block.confidence),
            bbox={
                "x": block.x,
                "y": block.y,
                "width": block.width,
                "height": block.height,
            },
            line_number=block.line_number,
            block_number=block.block_number,
        )
        for block in sorted(inspection.ocr_blocks, key=lambda b: (b.page_number, b.id))
    ]
    extraction = [
        ExtractedFieldOut(
            extracted_field_id=field.id,
            field_name=field.field_name,
            status=field.status,
            value=field.value_json,
            raw_text=field.raw_text,
            ocr_confidence=float(field.ocr_confidence) if field.ocr_confidence is not None else None,
            extraction_confidence=(
                float(field.extraction_confidence) if field.extraction_confidence is not None else None
            ),
            ai_confidence=float(field.ai_confidence) if field.ai_confidence is not None else None,
            resolution_status=field.resolution_status,
            method=field.method,
            evidence=[
                ExtractionEvidenceOut(ocr_block_id=ref.ocr_block_id, page_number=ref.page_number)
                for ref in field.evidence
            ],
            candidates=(
                [
                    FieldCandidateOut(
                        raw_text=c.get("raw_text"),
                        value=c.get("value"),
                        method=c.get("method", "deterministic"),
                        confidence=c.get("confidence"),
                        evidence=[
                            ExtractionEvidenceOut(
                                ocr_block_id=ref["ocr_block_id"],
                                page_number=ref.get("page_number", 1),
                            )
                            for ref in (c.get("evidence") or [])
                        ],
                    )
                    for c in inspection_service._candidate_outs(field)
                ]
                or None
            ),
        )
        for field in get_extracted_fields(session, inspection)
    ]
    latest = latest_evaluation(session, inspection)
    visual_records = evidence_service.get_visual_evidence(session, inspection)
    field_verifications = [
        verification_service.field_verification_out(v, session)
        for v in session.execute(
            select(FieldVerification).where(FieldVerification.inspection_id == inspection.id)
        )
        .scalars()
        .all()
    ]
    return InspectionOut(
        inspection_id=inspection.inspection_id,
        status=inspection.processing_status.value,
        created_at=inspection.created_at,
        file={
            "original_filename": inspection.original_filename or "",
            "document_type": inspection.document_type or "image",
        },
        ocr={
            "pages": pages,
            "blocks": blocks,
            "full_text": "\n\n".join(page.full_text for page in pages),
            "blocks_detected": len(blocks),
            "average_confidence": average_confidence(session, inspection.id),
        },
        extraction=ExtractionOut(fields=extraction),
        evaluation=(
            EvaluationOut(
                inspection_id=inspection.inspection_id,
                **verification_service.enrich_evaluation(
                    session, latest, evaluation_service.evaluation_out(latest)
                ),
                verification_required=any(r.requires_officer_verification for r in latest.rule_results),
            )
            if latest
            else None
        ),
        visual_evidence=evidence_service.evidence_out(visual_records),
        field_verifications=field_verifications,
    )


@router.get("/{inspection_id}")
def get_inspection(inspection_id: str, session: Session = Depends(get_db)) -> InspectionOut:
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    return _to_out(inspection, session)


@router.post("/{inspection_id}/evaluate", response_model=EvaluationOut)
def evaluate_inspection(inspection_id: str, session: Session = Depends(get_db)) -> EvaluationOut:
    """Run a new automated evaluation version over the persisted inspection."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    try:
        evaluation = evaluation_service.evaluate_inspection(session, inspection)
    except evaluation_service.ExtractionUnavailableError as exc:
        raise HTTPException(status_code=409, detail={"code": "EXTRACTION_NOT_AVAILABLE", "message": exc.message}) from exc
    except evaluation_service.LegalEngineError as exc:
        raise HTTPException(status_code=503, detail={"code": "LEGAL_ENGINE_UNAVAILABLE", "message": exc.message}) from exc
    return EvaluationOut(
        inspection_id=inspection.inspection_id,
        **verification_service.enrich_evaluation(
            session, evaluation, evaluation_service.evaluation_out(evaluation)
        ),
        verification_required=any(r.requires_officer_verification for r in evaluation.rule_results),
    )


@router.post("/{inspection_id}/evidence", response_model=list[VisualEvidenceOut])
def analyze_inspection_evidence(inspection_id: str, session: Session = Depends(get_db)) -> list[VisualEvidenceOut]:
    """Run CV evidence analysis and persist the measurements.

    CV failure leaves the inspection intact — evidence is optional and can
    be re-run at any time.
    """
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    try:
        records = evidence_service.run_evidence_analysis(session, inspection)
    except (evidence_service.CVServiceError, evidence_service.CVRejectionError) as exc:
        code = "CV_SERVICE_UNAVAILABLE" if isinstance(exc, evidence_service.CVServiceError) else exc.code
        raise HTTPException(status_code=503, detail={"code": code, "message": exc.message}) from exc
    session.commit()
    return [VisualEvidenceOut(**item) for item in evidence_service.evidence_out(records)]


@router.get("/{inspection_id}/evaluation", response_model=EvaluationOut)
def get_evaluation(inspection_id: str, session: Session = Depends(get_db)) -> EvaluationOut:
    """Latest persisted evaluation, 404 when none has been run yet."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    evaluation = latest_evaluation(session, inspection)
    if evaluation is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "EVALUATION_NOT_FOUND", "message": "No evaluation has been run for this inspection."},
        )
    return EvaluationOut(
        inspection_id=inspection.inspection_id,
        **verification_service.enrich_evaluation(
            session, evaluation, evaluation_service.evaluation_out(evaluation)
        ),
        verification_required=any(r.requires_officer_verification for r in evaluation.rule_results),
    )


@router.get("/{inspection_id}/image")
def get_inspection_image(inspection_id: str, session: Session = Depends(get_db)) -> FileResponse:
    """Serve the stored original upload (never exposes server paths)."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    if not inspection.file_path or inspection.processing_status is None:
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "No stored file for this inspection."})
    path = Path(inspection.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "Stored file is missing."})
    media_type = inspection.mime_type or (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=inspection.original_filename or path.name)


# --- Phase 8: officer verification (separate layer; originals immutable) ---


@router.post("/{inspection_id}/verifications", response_model=OfficerVerificationOut, status_code=201)
def create_rule_verification(
    inspection_id: str,
    payload: OfficerVerificationIn,
    session: Session = Depends(get_db),
) -> OfficerVerificationOut:
    """Record an officer decision on one rule of the latest evaluation.

    Verifications attach to the evaluation version they reviewed; a later
    re-evaluation is unverified until reviewed again. Originals untouched.
    """
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    evaluation = latest_evaluation(session, inspection)
    if evaluation is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "EVALUATION_NOT_FOUND", "message": "Run an assessment before verifying its rules."},
        )
    try:
        decision = OfficerDecision(payload.decision)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_DECISION", "message": f"Unknown decision '{payload.decision}'."},
        ) from exc
    verification = verification_service.create_verification(
        session,
        inspection,
        payload.rule_evaluation_id,
        decision,
        payload.comment,
        evidence_ocr_block_id=payload.evidence_ocr_block_id,
        evidence_visual_evidence_id=payload.evidence_visual_evidence_id,
        evidence_extracted_field_id=payload.evidence_extracted_field_id,
    )
    session.commit()
    return OfficerVerificationOut(**verification_service.verification_out(verification, session))


@router.get("/{inspection_id}/verifications", response_model=list[OfficerVerificationOut])
def list_rule_verifications(
    inspection_id: str, session: Session = Depends(get_db)
) -> list[OfficerVerificationOut]:
    """All officer verifications for the inspection, newest first."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    rows = (
        session.execute(
            select(OfficerVerification)
            .where(OfficerVerification.inspection_id == inspection.id)
            .order_by(OfficerVerification.id.desc())
        )
        .scalars()
        .all()
    )
    return [OfficerVerificationOut(**verification_service.verification_out(v, session)) for v in rows]


@router.post("/{inspection_id}/field-verifications", response_model=FieldVerificationOut, status_code=201)
def create_field_verification(
    inspection_id: str,
    payload: FieldVerificationIn,
    session: Session = Depends(get_db),
) -> FieldVerificationOut:
    """Verify (or correct) one extracted field. The original value stays."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    verification = verification_service.create_field_verification(
        session,
        inspection,
        payload.extracted_field_id,
        payload.verification_status,
        payload.verified_value,
        payload.comment,
        evidence_ocr_block_id=payload.evidence_ocr_block_id,
        evidence_visual_evidence_id=payload.evidence_visual_evidence_id,
    )
    session.commit()
    return FieldVerificationOut(**verification_service.field_verification_out(verification, session))


@router.get("/{inspection_id}/audit-log", response_model=list[AuditLogOut])
def get_audit_log(inspection_id: str, session: Session = Depends(get_db)) -> list[AuditLogOut]:
    """Append-only audit trail for the inspection, oldest first."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    rows = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.inspection_id == inspection.id)
            .order_by(AuditLog.id.asc())
        )
        .scalars()
        .all()
    )
    return [
        AuditLogOut(
            id=row.id,
            inspection_id=inspection.inspection_id,
            action=row.action,
            actor=row.actor,
            evaluation_id=row.evaluation_id,
            rule_evaluation_id=row.rule_evaluation_id,
            decision=row.decision,
            previous_state=row.previous_state,
            comment=row.comment,
            timestamp=row.timestamp,
        )
        for row in rows
    ]


# --- Phase 9: history, dashboard, evaluation versions, reports ---


@router.get("", response_model=InspectionHistoryOut)
def list_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses to match"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    search: str | None = Query(None, description="Inspection ID, product name or manufacturer"),
    session: Session = Depends(get_db),
) -> InspectionHistoryOut:
    """Paginated inspection history from PostgreSQL (summaries only)."""
    return InspectionHistoryOut(**history_service.list_inspections(
        session,
        page=page,
        page_size=page_size,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search=search,
    ))


@router.get("/dashboard/metrics", response_model=DashboardMetricsOut)
def dashboard_metrics(session: Session = Depends(get_db)) -> DashboardMetricsOut:
    """Database-backed overview metrics (zero-state honest: zeros when empty).

    Automated and officer-effective counts are reported side by side.
    """
    return DashboardMetricsOut(**history_service.dashboard_metrics(session))


@router.get("/{inspection_id}/evaluations", response_model=list[EvaluationVersionOut])
def list_evaluation_versions(
    inspection_id: str, session: Session = Depends(get_db)
) -> list[EvaluationVersionOut]:
    """All evaluation versions for the inspection (immutable history)."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    return [
        EvaluationVersionOut(**v) for v in history_service.list_evaluation_versions(session, inspection)
    ]


@router.get("/{inspection_id}/evaluations/{version}", response_model=EvaluationOut)
def get_evaluation_version(
    inspection_id: str, version: int, session: Session = Depends(get_db)
) -> EvaluationOut:
    """One specific evaluation version, view-only — history is never edited."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    payload = history_service.get_evaluation_version(session, inspection, version)
    return EvaluationOut(**payload)


@router.post("/{inspection_id}/report", response_model=ReportOut, status_code=201)
def generate_report(inspection_id: str, session: Session = Depends(get_db)) -> ReportOut:
    """Generate the PDF report for the latest evaluation version.

    Re-generating for the same evaluation returns the existing report —
    reports are immutable and bound to their evaluation version.
    """
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    try:
        report = report_service.generate_report(session, inspection)
    except report_service.ReportError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "REPORT_NOT_POSSIBLE", "message": exc.message},
        ) from exc
    session.commit()
    return ReportOut(**report_service.report_out(report, session))


@router.get("/{inspection_id}/report", response_model=ReportOut)
def get_report(inspection_id: str, session: Session = Depends(get_db)) -> ReportOut:
    """Latest report metadata for the inspection (404 before first generation)."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    from app.models.inspection import InspectionReport

    report = (
        session.execute(
            select(InspectionReport)
            .where(InspectionReport.inspection_id == inspection.id)
            .order_by(InspectionReport.evaluation_version.desc(), InspectionReport.id.desc())
        )
        .scalars()
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "message": "No report generated for this inspection."},
        )
    return ReportOut(**report_service.report_out(report, session))


@router.get("/{inspection_id}/report/download")
def download_report(inspection_id: str, session: Session = Depends(get_db)) -> FileResponse:
    """Serve the stored PDF for the latest report (integrity hash in metadata)."""
    inspection = inspection_service.get_inspection_by_public_id(session, inspection_id)
    from app.models.inspection import InspectionReport

    report = (
        session.execute(
            select(InspectionReport)
            .where(InspectionReport.inspection_id == inspection.id)
            .order_by(InspectionReport.evaluation_version.desc(), InspectionReport.id.desc())
        )
        .scalars()
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_NOT_FOUND", "message": "No report generated for this inspection."},
        )
    path = Path(get_settings().upload_dir) / report.storage_reference
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "REPORT_FILE_MISSING", "message": "The report file is missing from storage."},
        )
    filename = f"{inspection.inspection_id}-assessment-v{report.evaluation_version}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)
