"""Inspection history, dashboard metrics and evaluation-version listing (Phase 9).

Read-only services over persisted data. History rows are summaries — no OCR
blocks, evidence or audit logs are loaded per row (no N+1: verifications and
evaluations for a page are fetched in bulk). Officer decisions layer beside
automated results; both are reported, neither replaces the other.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.inspection import (
    ExtractedField,
    Inspection,
    InspectionEvaluation,
    OfficerDecision,
    OfficerVerification,
    RuleEvaluation,
)
from app.services.verification_service import effective_status_for


def _fail(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# Rollups shown by the dashboard / history. Derived exactly like the
# evaluation services do — no score, no certification language.
AUTOMATED_STATUS_ORDER = ("NON_COMPLIANT", "REVIEW_REQUIRED", "INCOMPLETE", "COMPLIANT")


def _overall_from_statuses(statuses: set[str]) -> str:
    if "VIOLATION" in statuses:
        return "NON_COMPLIANT"
    if "REVIEW_REQUIRED" in statuses:
        return "REVIEW_REQUIRED"
    if "NOT_VERIFIABLE" in statuses or "NOT_APPLICABLE" in statuses:
        return "INCOMPLETE"
    return "COMPLIANT"


def _field_text(field: ExtractedField) -> str | None:
    """First text value inside a field's value_json (shape per ai/app/extraction)."""
    value = field.value_json
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _display_fields(
    session: Session, inspection_ids: list[int], names: list[str]
) -> dict[int, dict[str, str | None]]:
    """Bulk-load detected display fields for a set of inspections."""
    if not inspection_ids:
        return {}
    fields = (
        session.execute(
            select(ExtractedField).where(
                ExtractedField.inspection_id.in_(inspection_ids),
                ExtractedField.field_name.in_(names),
                ExtractedField.status == "detected",
            )
        )
        .scalars()
        .all()
    )
    out: dict[int, dict[str, str | None]] = {}
    for f in fields:
        slot = out.setdefault(f.inspection_id, {})
        if f.field_name not in slot:
            slot[f.field_name] = _field_text(f)
    return out


def _latest_evaluations(
    session: Session, inspection_ids: list[int]
) -> dict[int, InspectionEvaluation]:
    """Latest evaluation per inspection, one query for the whole page."""
    if not inspection_ids:
        return {}
    rows = (
        session.execute(
            select(InspectionEvaluation)
            .where(InspectionEvaluation.inspection_id.in_(inspection_ids))
            .order_by(
                InspectionEvaluation.inspection_id,
                InspectionEvaluation.evaluation_version.desc(),
            )
        )
        .scalars()
        .all()
    )
    latest: dict[int, InspectionEvaluation] = {}
    for row in rows:  # ordered desc per inspection → first seen wins
        latest.setdefault(row.inspection_id, row)
    return latest


def _effective_by_evaluation(
    session: Session, evaluation_ids: list[int]
) -> dict[int, tuple[dict[str, str], dict[str, OfficerVerification | None]]]:
    """Per evaluation: {rule_id: effective_status} and {rule_id: latest verification}.

    Two bulk queries for the whole page — no per-row verification lookups.
    """
    out: dict[int, tuple[dict[str, str], dict[str, OfficerVerification | None]]] = {
        eid: ({}, {}) for eid in evaluation_ids
    }
    if not evaluation_ids:
        return out
    rules = (
        session.execute(
            select(RuleEvaluation).where(
                RuleEvaluation.inspection_evaluation_id.in_(evaluation_ids)
            )
        )
        .scalars()
        .all()
    )
    rules_by_eval: dict[int, list[RuleEvaluation]] = {}
    for r in rules:
        rules_by_eval.setdefault(r.inspection_evaluation_id, []).append(r)

    verifications = (
        session.execute(
            select(OfficerVerification)
            .where(OfficerVerification.rule_evaluation_id.in_([r.id for r in rules] or [0]))
            .order_by(OfficerVerification.id.desc())
        )
        .scalars()
        .all()
    )
    latest_verification: dict[int, OfficerVerification] = {}
    for v in verifications:  # id desc → first seen per rule wins
        latest_verification.setdefault(v.rule_evaluation_id, v)

    for eid, eval_rules in rules_by_eval.items():
        effective: dict[str, str] = {}
        officers: dict[str, OfficerVerification | None] = {}
        for rule in eval_rules:
            verification = latest_verification.get(rule.id)
            effective[rule.rule_id] = effective_status_for(verification, rule)
            officers[rule.rule_id] = verification
        out[eid] = (effective, officers)
    return out


def _rollup(statuses: set[str]) -> str:
    return _overall_from_statuses(statuses)


def _search_matching_ids(session: Session, search: str):
    """Scalar subquery of inspection pks matching the search needle.

    Matches the public inspection id, or the persisted product name /
    manufacturer values (JSON text cast, lowercased) — enough for useful
    lookup without full-text infrastructure.
    """
    needle = f"%{search.strip().lower()}%"
    field_match = select(ExtractedField.inspection_id).where(
        ExtractedField.field_name.in_(["product_name", "manufacturer"]),
        ExtractedField.status == "detected",
        func.lower(cast(ExtractedField.value_json, String)).like(needle),
    )
    return select(Inspection.id).where(
        or_(
            func.lower(Inspection.inspection_id).like(needle),
            Inspection.id.in_(field_match),
        )
    )


def _rollup_expr(violation_flag, review_flag, incomplete_flag):
    """Inspection-level rollup over rule-status flags, mirroring the
    evaluation services' overall_status(): NON_COMPLIANT on any violation,
    else REVIEW_REQUIRED, else INCOMPLETE, else COMPLIANT. Never a score."""
    return case(
        (violation_flag == 1, "NON_COMPLIANT"),
        (review_flag == 1, "REVIEW_REQUIRED"),
        (incomplete_flag == 1, "INCOMPLETE"),
        else_="COMPLIANT",
    )


def _rule_effective_expr():
    """Per-rule effective status in SQL, mirroring
    verification_service.effective_status_for(): the latest verification's
    decision (highest id) drives the outcome; without one — or on ACCEPT —
    the automated status stands."""
    latest_decision = (
        select(OfficerVerification.decision)
        .where(OfficerVerification.rule_evaluation_id == RuleEvaluation.id)
        .order_by(OfficerVerification.id.desc())
        .limit(1)
        .scalar_subquery()
        .correlate(RuleEvaluation)
    )
    return case(
        (latest_decision == OfficerDecision.OVERRIDE_COMPLIANT.value, "COMPLIANT"),
        (latest_decision == OfficerDecision.OVERRIDE_VIOLATION.value, "VIOLATION"),
        (latest_decision == OfficerDecision.CONFIRM_REVIEW_REQUIRED.value, "REVIEW_REQUIRED"),
        (latest_decision == OfficerDecision.CONFIRM_NOT_VERIFIABLE.value, "NOT_VERIFIABLE"),
        (latest_decision == OfficerDecision.CONFIRM_NOT_APPLICABLE.value, "NOT_APPLICABLE"),
        else_=RuleEvaluation.status,
    )


def _status_per_inspection_sq():
    """Automated + officer-effective rollups for each inspection's LATEST
    evaluation, computed in SQL so filters apply before pagination.

    Rows are (inspection_id, automated_status, effective_rollup, has_verif).
    Inspections without an evaluation produce no row here (outer-joined away
    as NULL on the inspection side), matching the previous display logic.
    """
    latest_version = (
        select(
            InspectionEvaluation.inspection_id.label("inspection_id"),
            func.max(InspectionEvaluation.evaluation_version).label("max_version"),
        )
        .group_by(InspectionEvaluation.inspection_id)
        .subquery()
    )
    effective = _rule_effective_expr()
    rollup = (
        select(
            RuleEvaluation.inspection_evaluation_id.label("eval_id"),
            func.max(case((RuleEvaluation.status == "VIOLATION", 1), else_=0)).label("a_viol"),
            func.max(case((RuleEvaluation.status == "REVIEW_REQUIRED", 1), else_=0)).label("a_review"),
            func.max(
                case((RuleEvaluation.status.in_(("NOT_VERIFIABLE", "NOT_APPLICABLE")), 1), else_=0)
            ).label("a_incomp"),
            func.max(case((effective == "VIOLATION", 1), else_=0)).label("e_viol"),
            func.max(case((effective == "REVIEW_REQUIRED", 1), else_=0)).label("e_review"),
            func.max(case((effective.in_(("NOT_VERIFIABLE", "NOT_APPLICABLE")), 1), else_=0)).label("e_incomp"),
            func.max(case((OfficerVerification.id.is_not(None), 1), else_=0)).label("has_verif"),
        )
        .select_from(RuleEvaluation)
        .outerjoin(OfficerVerification, OfficerVerification.rule_evaluation_id == RuleEvaluation.id)
        .group_by(RuleEvaluation.inspection_evaluation_id)
        .subquery()
    )
    return (
        select(
            InspectionEvaluation.inspection_id.label("inspection_id"),
            latest_version.c.max_version.label("evaluation_version"),
            _rollup_expr(rollup.c.a_viol, rollup.c.a_review, rollup.c.a_incomp).label("automated_status"),
            _rollup_expr(rollup.c.e_viol, rollup.c.e_review, rollup.c.e_incomp).label("effective_rollup"),
            rollup.c.has_verif.label("has_verif"),
        )
        .join(
            latest_version,
            and_(
                InspectionEvaluation.inspection_id == latest_version.c.inspection_id,
                InspectionEvaluation.evaluation_version == latest_version.c.max_version,
            ),
        )
        .outerjoin(rollup, rollup.c.eval_id == InspectionEvaluation.id)
        .subquery()
    )


def list_inspections(
    session: Session,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
) -> dict:
    """Paginated inspection summaries with per-inspection status rollups.

    Every filter (status, dates, search) is part of the SQL WHERE clause
    before LIMIT/OFFSET, so total/pages describe the full filtered set and no
    matching row can be missed because it lives on another page. Status
    semantics are unchanged: a row matches when its automated status OR its
    officer-effective status is in the requested set.
    """
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    conditions = []
    if date_from is not None:
        conditions.append(Inspection.created_at >= date_from)
    if date_to is not None:
        conditions.append(Inspection.created_at < date_to)
    if search and search.strip():
        conditions.append(Inspection.id.in_(_search_matching_ids(session, search)))

    status_sq = _status_per_inspection_sq()
    if status and status.strip():
        wanted = {s.strip().upper() for s in status.split(",") if s.strip()}
        if wanted:
            conditions.append(
                Inspection.id.in_(
                    select(status_sq.c.inspection_id).where(
                        or_(
                            status_sq.c.automated_status.in_(wanted),
                            status_sq.c.effective_rollup.in_(wanted),
                        )
                    )
                )
            )

    base = select(Inspection).where(*conditions)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    pages = (total + page_size - 1) // page_size

    rows = session.execute(
        select(
            Inspection,
            status_sq.c.automated_status,
            status_sq.c.effective_rollup,
            status_sq.c.has_verif,
            status_sq.c.evaluation_version,
        )
        .outerjoin(status_sq, status_sq.c.inspection_id == Inspection.id)
        .where(*conditions)
        .order_by(Inspection.created_at.desc(), Inspection.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    page_ids = [row[0].id for row in rows]
    display = _display_fields(
        session, page_ids, ["product_name", "manufacturer", "net_quantity", "mrp"]
    )

    items = []
    for inspection, automated, officer_effective, has_verif, evaluation_version in rows:
        items.append(
            {
                "inspection_id": inspection.inspection_id,
                "product_name": display.get(inspection.id, {}).get("product_name"),
                "inspection_date": inspection.created_at,
                "automated_status": automated,
                "officer_verified_status": officer_effective,
                "effective_status": officer_effective or automated,
                "evaluation_version": evaluation_version,
                "verification_required": bool(has_verif),
                "has_evaluation": automated is not None,
                "created_at": inspection.created_at,
                "updated_at": inspection.updated_at,
            }
        )

    return {"items": items, "page": page, "page_size": page_size, "total": total, "pages": pages}


def dashboard_metrics(session: Session) -> dict:
    """Database-backed overview counts (automated and officer-effective).

    Zero-state honest: an empty database yields zeros, never demo numbers.
    """
    inspections = session.execute(select(Inspection)).scalars().all()
    automated_counts = {s: 0 for s in AUTOMATED_STATUS_ORDER}
    effective_counts = {s: 0 for s in AUTOMATED_STATUS_ORDER}

    latest_by_inspection = _latest_evaluations(session, [i.id for i in inspections])
    effective_info = _effective_by_evaluation(
        session, [e.id for e in latest_by_inspection.values()]
    )
    for inspection in inspections:
        evaluation = latest_by_inspection.get(inspection.id)
        if evaluation is None:
            continue  # no evaluation yet — counted only in totals
        automated_counts[evaluation.overall_status] = (
            automated_counts.get(evaluation.overall_status, 0) + 1
        )
        effective_map, _ = effective_info.get(evaluation.id, ({}, {}))
        officer_rollup = _rollup(set(effective_map.values())) if effective_map else evaluation.overall_status
        effective_counts[officer_rollup] = effective_counts.get(officer_rollup, 0) + 1

    display = _display_fields(
        session, [i.id for i in inspections], ["product_name"]
    )
    ordered = sorted(inspections, key=lambda i: (i.created_at, i.id), reverse=True)[:5]
    recent = []
    for inspection in ordered:
        evaluation = latest_by_inspection.get(inspection.id)
        effective_map, _ = (
            effective_info.get(evaluation.id, ({}, {})) if evaluation else ({}, {})
        )
        recent.append(
            {
                "inspection_id": inspection.inspection_id,
                "product_name": display.get(inspection.id, {}).get("product_name"),
                "created_at": inspection.created_at,
                "automated_status": evaluation.overall_status if evaluation else None,
                "effective_status": (
                    _rollup(set(effective_map.values())) if evaluation and effective_map else (
                        evaluation.overall_status if evaluation else None
                    )
                ),
            }
        )

    return {
        "total_inspections": len(inspections),
        "automated": automated_counts,
        "officer_effective": effective_counts,
        "recent_inspections": recent,
    }


def list_evaluation_versions(session: Session, inspection: Inspection) -> list[dict]:
    """All evaluation versions for an inspection (immutable history)."""
    rows = (
        session.execute(
            select(InspectionEvaluation)
            .where(InspectionEvaluation.inspection_id == inspection.id)
            .order_by(InspectionEvaluation.evaluation_version.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    verifications = (
        session.execute(
            select(OfficerVerification.inspection_evaluation_id)
            .where(OfficerVerification.inspection_evaluation_id.in_([r.id for r in rows]))
        )
        .scalars()
        .all()
    )
    verified_evaluations = set(verifications)
    versions = []
    for row in rows:
        versions.append(
            {
                "evaluation_id": row.id,
                "evaluation_version": row.evaluation_version,
                "engine_version": row.engine_version,
                "overall_status": row.overall_status,
                "created_at": row.created_at,
                "has_officer_verification": row.id in verified_evaluations,
            }
        )
    return versions


def get_evaluation_version(session: Session, inspection: Inspection, version: int) -> dict:
    """One specific evaluation version, enriched like the latest-evaluation view."""
    row = (
        session.execute(
            select(InspectionEvaluation)
            .where(
                InspectionEvaluation.inspection_id == inspection.id,
                InspectionEvaluation.evaluation_version == version,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise _fail(
            404,
            "EVALUATION_VERSION_NOT_FOUND",
            f"No evaluation version {version} for this inspection.",
        )
    from app.services import evaluation_service, verification_service

    payload = verification_service.enrich_evaluation(
        session, row, evaluation_service.evaluation_out(row)
    )
    payload["inspection_id"] = inspection.inspection_id
    payload["verification_required"] = any(
        r.requires_officer_verification for r in row.rule_results
    )
    return payload
