"""Inspection Assessment Report generation (Phase 9).

Builds a text-based PDF from persisted database data only — no OCR, AI or CV
re-runs. A report belongs to exactly one evaluation version; the SHA-256 of
the PDF bytes is stored for file-integrity verification (this is NOT a digital
signature). The disclaimer is mandatory on every report.
"""
import hashlib
import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.inspection import (
    AuditLog,
    ExtractedField,
    FieldVerification,
    Inspection,
    InspectionEvaluation,
    InspectionReport,
    OfficerVerification,
    RuleEvaluation,
    VisualEvidenceRecord,
)
from app.services import evaluation_service, verification_service

logger = logging.getLogger(__name__)

LEGAL_SOURCE = "Legal Metrology (Packaged Commodities) Rules, 2011"
DISCLAIMER = (
    "This report represents an automated compliance assessment and, where "
    "applicable, an officer verification record. It is not a legal certification."
)

# Display fields surfaced in the Product Information section (names per the
# AI service's extraction schema; only detected fields are printed).
_PRODUCT_FIELDS = [
    "product_name",
    "manufacturer",
    "packer",
    "importer",
    "marketer",
    "manufacturer_address",
    "packer_address",
    "importer_address",
    "net_quantity",
    "mrp",
    "manufacturing_date",
    "packing_date",
    "best_before",
    "use_by",
    "expiry_date",
    "consumer_care",
    "batch_number",
    "lot_number",
    "country_of_origin",
]
_FIELD_LABELS = {
    "product_name": "Product name",
    "manufacturer": "Manufacturer",
    "packer": "Packer",
    "importer": "Importer",
    "marketer": "Marketer",
    "manufacturer_address": "Manufacturer address",
    "packer_address": "Packer address",
    "importer_address": "Importer address",
    "net_quantity": "Net quantity",
    "mrp": "Retail sale price (MRP)",
    "manufacturing_date": "Manufacture date",
    "packing_date": "Packing date",
    "best_before": "Best before",
    "use_by": "Use by",
    "expiry_date": "Expiry date",
    "consumer_care": "Consumer care",
    "batch_number": "Batch number",
    "lot_number": "Lot number",
    "country_of_origin": "Country of origin",
}


class ReportError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "brand", parent=base["Title"], fontSize=20, textColor=colors.HexColor("#1B4332"), spaceAfter=2
        ),
        "doc_title": ParagraphStyle(
            "doc_title", parent=base["Heading2"], fontSize=13, textColor=colors.HexColor("#40513B"), spaceAfter=10
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=12,
            textColor=colors.HexColor("#1B4332"),
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9, leading=12),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#6B7280")
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#7C2D12")
        ),
    }


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%d %b %Y, %H:%M UTC") if value else "—"


NOT_DETECTED_TEXT = "Not detected from available evidence"


def _field_display(value) -> str | None:
    """Render a persisted extraction value without inventing content.

    Structured values are rendered according to their shape (e.g. the MRP
    ``{"amount": 30.0, "currency": "INR"}`` becomes "INR 30.00") — never by
    picking an arbitrary member such as the currency alone.
    """
    if isinstance(value, dict):
        if isinstance(value.get("amount"), (int, float)):
            amount = f"{float(value['amount']):,.2f}"
            currency = value.get("currency")
            return f"{currency} {amount}" if currency else amount
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, (int, float)):
                return f"{v:g}"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _scalar(value) -> str | None:
    """Best-effort text for a persisted scalar/structured attribute."""
    return _field_display(value)


def _info_text(value) -> str | None:
    """Render rule-level required/actual information.

    These arrive as a list of required field names and a dict of actual
    values (persisted JSON on the rule evaluation).
    """
    if isinstance(value, dict) and value:
        parts = [f"{k}: {v}" for k in value if (v := _field_display(value[k]))]
        return "; ".join(parts) or None
    if isinstance(value, (list, tuple)) and value:
        return ", ".join(str(v) for v in value) or None
    return _field_display(value)


def _kv_table(rows: list[tuple[str, str]], styles) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", styles["body"]), Paragraph(v, styles["body"])] for k, v in rows]
    table = Table(data, colWidths=[55 * mm, 115 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _grid_table(header: list[str], rows: list[list[str]], widths: list[float], styles) -> Table:
    table = Table(
        [[Paragraph(f"<b>{h}</b>", styles["small"]) for h in header]]
        + [[Paragraph(str(c), styles["small"]) for c in row] for row in rows],
        colWidths=widths,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _product_rows(session: Session, inspection: Inspection) -> list[tuple[str, str]]:
    fields = (
        session.execute(select(ExtractedField).where(ExtractedField.inspection_id == inspection.id))
        .scalars()
        .all()
    )
    by_name = {f.field_name: f for f in fields}
    rows = []
    for name in _PRODUCT_FIELDS:
        label = _FIELD_LABELS.get(name, name)
        field = by_name.get(name)
        if field is None:
            # In the spec'd display list but never extracted at all.
            rows.append((label, NOT_DETECTED_TEXT))
            continue
        if field.status == "detected":
            display = _field_display(field.value_json)
            if display:
                rows.append((label, display))
            continue
        # Detected-elsewhere statuses are shown as their raw state; an
        # explicit NOT_DETECTED must never be silently upgraded or dropped.
        rows.append((label, NOT_DETECTED_TEXT if field.status == "not_detected" else field.status))
    return rows


def build_report_pdf(session: Session, inspection: Inspection, evaluation: InspectionEvaluation) -> bytes:
    """Render the PDF for one evaluation version and return the bytes."""
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Inspection Assessment Report",
        author="LabelGuard AI",
        # Uncompressed content streams keep the report text directly
        # inspectable (and integrity-verifiable) without extra tooling.
        pageCompression=0,
    )

    enriched = verification_service.enrich_evaluation(
        session, evaluation, evaluation_service.evaluation_out(evaluation)
    )
    product_rows = _product_rows(session, inspection)
    product_name = next((v for k, v in product_rows if k == "Product name"), None)

    story = []

    # ---- Header -------------------------------------------------------------
    story.append(Paragraph("LabelGuard AI", styles["brand"]))
    story.append(Paragraph("Inspection Assessment Report", styles["doc_title"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1B4332")))

    # ---- Inspection summary ---------------------------------------------------
    story.append(Paragraph("Inspection Summary", styles["h2"]))
    summary_rows = [
        ("Inspection ID", inspection.inspection_id),
        ("Inspection date", _fmt_dt(inspection.created_at)),
        ("Evaluation version", f"v{evaluation.evaluation_version}"),
        ("Engine version", evaluation.engine_version),
        ("Automated assessment", evaluation.overall_status),
        (
            "Officer-verified assessment",
            enriched.get("officer_effective_status") or evaluation.overall_status,
        ),
    ]
    if product_name:
        summary_rows.insert(2, ("Product", product_name))
    story.append(_kv_table(summary_rows, styles))

    # ---- Product information ------------------------------------------------------
    if product_rows:
        story.append(Paragraph("Product Information", styles["h2"]))
        story.append(_kv_table(product_rows, styles))
        story.append(
            Paragraph(
                "Values are the system's extracted information. Officer-verified values, "
                "when present, are recorded in the Officer Verification section.",
                styles["small"],
            )
        )

    # ---- Automated assessment (per rule) ---------------------------------------------
    story.append(Paragraph("Automated Assessment — Rule Results", styles["h2"]))
    for result in enriched["results"]:
        confidence = result.get("confidence")
        conf_text = f"{round(confidence * 100)}%" if confidence is not None else "—"
        officer = result.get("officer_verification")
        story.append(Paragraph(f"<b>{result['rule_number']} — {result['rule_title']}</b>", styles["body"]))
        status_line = f"Status: {result['status']}"
        if result.get("severity"):
            status_line += f" · Severity: {result['severity']}"
        if officer:
            status_line += f" · Effective: {result.get('effective_status')}"
        story.append(Paragraph(status_line, styles["body"]))
        story.append(Paragraph(f"Finding: {result['finding']}", styles["body"]))
        required = _info_text(result.get("required_information"))
        if required:
            story.append(Paragraph(f"Required information: {required}", styles["body"]))
        actual = _info_text(result.get("actual_information"))
        if actual:
            story.append(Paragraph(f"Actual information: {actual}", styles["body"]))
        story.append(Paragraph(f"Confidence: {conf_text}", styles["body"]))
        story.append(
            Paragraph(
                "Officer verification: " + ("recorded below" if officer else "Not yet verified"),
                styles["body"],
            )
        )
        evidence_refs = []
        for ev in result.get("evidence") or []:
            ref = ev.get("evidence_reference") or ev.get("field_name") or ""
            blocks = ev.get("ocr_block_ids") or ([ev["ocr_block_id"]] if ev.get("ocr_block_id") else [])
            for block_id in blocks:
                evidence_refs.append(f"OCR block {block_id}" + (f" ({ref})" if ref else ""))
            if not blocks and ref:
                evidence_refs.append(ref)
        if evidence_refs:
            story.append(Paragraph("Evidence: " + "; ".join(evidence_refs[:8]), styles["small"]))
        story.append(Spacer(1, 5))

    # ---- Visual evidence ---------------------------------------------------------------
    visual = (
        session.execute(
            select(VisualEvidenceRecord).where(VisualEvidenceRecord.inspection_id == inspection.id)
        )
        .scalars()
        .all()
    )
    if visual:
        story.append(Paragraph("Visual Evidence", styles["h2"]))
        rows = []
        for item in visual[:30]:
            value = (
                f"{item.value_numeric:g} {item.unit}"
                if item.value_numeric is not None
                else (item.value_text or "—")
            )
            rows.append(
                [
                    item.evidence_type,
                    value,
                    f"{round(float(item.confidence) * 100)}%" if item.confidence is not None else "—",
                    item.method,
                    item.verification_status,
                ]
            )
        story.append(
            _grid_table(
                ["Type", "Value", "Conf.", "Method", "Status"],
                rows,
                [38 * mm, 40 * mm, 14 * mm, 44 * mm, 34 * mm],
                styles,
            )
        )
        story.append(
            Paragraph("Visual measurements are automated observations, not legal judgments.", styles["small"])
        )

    # ---- Officer verification ------------------------------------------------------------
    verifications = (
        session.execute(
            select(OfficerVerification)
            .where(OfficerVerification.inspection_evaluation_id == evaluation.id)
            .order_by(OfficerVerification.id.asc())
        )
        .scalars()
        .all()
    )
    field_verifications = (
        session.execute(
            select(FieldVerification).where(FieldVerification.inspection_id == inspection.id)
        )
        .scalars()
        .all()
    )
    if verifications or field_verifications:
        story.append(Paragraph("Officer Verification", styles["h2"]))
        for v in verifications:
            rule = session.get(RuleEvaluation, v.rule_evaluation_id)
            title = (
                f"{rule.rule_number} — {rule.rule_title}"
                if rule
                else f"rule evaluation #{v.rule_evaluation_id}"
            )
            story.append(
                _kv_table(
                    [
                        ("Rule", title),
                        ("Decision", v.decision.value),
                        ("Officer", v.officer_identifier),
                        ("Comment", v.comment or "—"),
                        ("Verified at", _fmt_dt(v.created_at)),
                        ("Evaluation version", f"v{evaluation.evaluation_version}"),
                    ],
                    styles,
                )
            )
            story.append(Spacer(1, 5))
        for v in field_verifications:
            field = session.get(ExtractedField, v.extracted_field_id)
            label = _FIELD_LABELS.get(field.field_name, field.field_name) if field else "field"
            story.append(
                _kv_table(
                    [
                        ("Field", label),
                        ("Verification", v.verification_status),
                        ("Officer-verified value", _field_display(v.verified_value) or "—"),
                        ("Officer", v.officer_identifier),
                        ("Comment", v.comment or "—"),
                        ("Verified at", _fmt_dt(v.created_at)),
                    ],
                    styles,
                )
            )
            story.append(Spacer(1, 5))

    # ---- Audit information ----------------------------------------------------------------
    audits = (
        session.execute(
            select(AuditLog).where(AuditLog.inspection_id == inspection.id).order_by(AuditLog.id.asc()).limit(40)
        )
        .scalars()
        .all()
    )
    if audits:
        story.append(Paragraph("Audit Information (append-only history)", styles["h2"]))
        rows = [
            [_fmt_dt(a.timestamp), a.actor, a.action, a.decision or "—", a.previous_state or "—"]
            for a in audits
        ]
        story.append(
            _grid_table(
                ["Timestamp", "Actor", "Action", "Decision", "Previous"],
                rows,
                [34 * mm, 26 * mm, 42 * mm, 38 * mm, 30 * mm],
                styles,
            )
        )

    # ---- Legal source + disclaimer ------------------------------------------------------------
    story.append(Paragraph("Legal Source", styles["h2"]))
    story.append(Paragraph(LEGAL_SOURCE, styles["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(DISCLAIMER, styles["disclaimer"]))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(
            18 * mm,
            10 * mm,
            f"{inspection.inspection_id} · Evaluation v{evaluation.evaluation_version} · Generated {_fmt_dt(datetime.now())}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def generate_report(session: Session, inspection: Inspection) -> InspectionReport:
    """Generate (or reuse) the report for the latest evaluation version.

    Reusing an existing report for the same evaluation keeps reports immutable:
    a later evaluation produces a new report and never rewrites this one.
    """
    evaluation = evaluation_service.latest_evaluation(session, inspection)
    if evaluation is None:
        raise ReportError("No evaluation has been run for this inspection.")
    existing = (
        session.execute(
            select(InspectionReport).where(InspectionReport.evaluation_id == evaluation.id)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    pdf_bytes = build_report_pdf(session, inspection, evaluation)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    relative = f"reports/{inspection.inspection_id}-v{evaluation.evaluation_version}.pdf"
    path = Path(get_settings().upload_dir) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)

    report = InspectionReport(
        inspection_id=inspection.id,
        evaluation_id=evaluation.id,
        evaluation_version=evaluation.evaluation_version,
        report_hash=digest,
        storage_reference=relative,
    )
    session.add(report)
    session.flush()
    return report


def report_out(report: InspectionReport, session: Session) -> dict:
    inspection = session.get(Inspection, report.inspection_id)
    return {
        "id": report.id,
        "inspection_id": inspection.inspection_id if inspection else "",
        "evaluation_id": report.evaluation_id,
        "evaluation_version": report.evaluation_version,
        "report_hash": report.report_hash,
        "storage_reference": report.storage_reference,
        "generated_at": report.generated_at,
    }
