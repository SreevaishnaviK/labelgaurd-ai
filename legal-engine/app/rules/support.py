"""Shared evaluator helpers.

The missing-evidence policy lives here once, so every rule group applies it
identically: a declaration counts as established-absent (VIOLATION) only when
the pipeline affirms the whole label was captured and read
(visual_evidence.label_fully_processed); otherwise the result is
NOT_VERIFIABLE. Missing information is never silently converted into a
violation.
"""
from app.rules.rule_model import RuleDefinition, RuleResult
from app.schemas.evaluation import EvaluationInput


def _base(rule: RuleDefinition) -> dict:
    return {
        "rule_id": rule.rule_id,
        "rule_number": rule.rule_number,
        "title": rule.title,
        "severity": rule.severity,
        "required_information": list(rule.required_fields),
        "source": {"document": rule.source_document, "page": rule.source_page},
    }


def result(
    rule: RuleDefinition,
    status: str,
    finding: str,
    *,
    actual: dict | None = None,
    evidence: list | None = None,
    officer_verification: bool = False,
) -> RuleResult:
    return RuleResult(
        **_base(rule),
        status=status,
        finding=finding,
        actual_information=actual or {},
        evidence=evidence or [],
        requires_officer_verification=officer_verification,
    )


def absence_is_established(data: EvaluationInput) -> bool:
    """Can the supplied evidence establish that a declaration is ABSENT?

    Only when the pipeline affirms the full label was captured and processed.
    OCR failures, cropped photos, or unknown capture quality cannot.
    """
    return data.visual_evidence.label_fully_processed is True


def field_absent(data: EvaluationInput, field: str) -> bool:
    return getattr(data.product, field, None) is None


def not_applicable(rule: RuleDefinition, reason: str) -> RuleResult:
    return result(rule, "NOT_APPLICABLE", reason)


def not_verifiable(
    rule: RuleDefinition,
    reason: str,
    *,
    officer_verification: bool = False,
    actual: dict | None = None,
) -> RuleResult:
    return result(rule, "NOT_VERIFIABLE", reason, actual=actual, officer_verification=officer_verification)
