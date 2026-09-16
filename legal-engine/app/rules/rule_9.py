"""Rule 9 — manner of making declarations (legibility, prominence, language).

Subjective visual judgments (is it "legible"? is it "prominent"?) are NOT
approximated with arbitrary thresholds. The deterministic checks here run
only on supplied evidence: contrast measurements and language detection.
Without them the result is REVIEW_REQUIRED (a human must judge legibility)
— never an automatic violation.
"""
from app.rules import support
from app.rules.rule_model import (
    Applicability,
    EvaluationType,
    RuleDefinition,
    RuleResult,
    Severity,
)
from app.schemas.evaluation import EvaluationInput


def _definition(rule_id: str, title: str, description: str) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        rule_number="9",
        title=title,
        description=description,
        source_page=None,
        applicability=[Applicability.RETAIL],
        severity=Severity.MANDATORY,
        evaluation_type=EvaluationType.FORMAT,
    )


def _evaluate_contrast(data: EvaluationInput) -> RuleResult:
    rule = RULE_9_RULES[0][0]
    ratio = data.visual_evidence.contrast_ratio
    measurements = data.visual_evidence.contrast_measurements
    if ratio is None and not measurements:
        return support.result(
            rule,
            "REVIEW_REQUIRED",
            "Legibility and prominence are visual judgments; no contrast "
            "measurement was supplied, so a human must review the label.",
            officer_verification=True,
        )
    values = [float(m["contrast"]) for m in measurements if isinstance(m.get("contrast"), (int, float))]
    if ratio is None:
        ratio = min(values) if values else None  # weakest region is the binding one
    if ratio is None:
        return support.result(
            rule,
            "REVIEW_REQUIRED",
            "Contrast measurements were supplied but none carried a usable "
            "value; requires review.",
            actual={"measurements": len(measurements)},
            officer_verification=True,
        )
    # A measured contrast exists, but Rule 9's exact requirement has not been
    # verified against the supplied PDF — no threshold is invented here.
    return support.result(
        rule,
        "REVIEW_REQUIRED",
        "Contrast was measured but the Rule 9 requirement has not yet been "
        "verified against the supplied PDF; requires review.",
        actual={
            "measured_contrast_ratio": ratio,
            "measurement_count": len(measurements) or 1,
        },
        officer_verification=True,
    )


def _evaluate_language(data: EvaluationInput) -> RuleResult:
    rule = RULE_9_RULES[1][0]
    language = data.visual_evidence.declaration_language
    if language is None:
        return support.result(
            rule,
            "NOT_VERIFIABLE",
            "Declaration language was not determined by the pipeline; the "
            "language requirement cannot be checked automatically.",
            officer_verification=True,
        )
    return support.result(
        rule,
        "REVIEW_REQUIRED",
        "Declaration language was detected but the required language(s) have "
        "not been verified against the supplied PDF; requires review.",
        actual={"detected_language": language},
        officer_verification=True,
    )


RULE_9_RULES = [
    (
        _definition(
            "LMPC-R9-A",
            "Legible and prominent declarations",
            "Declarations must be made legibly, prominently, and in the "
            "specified manner; visual quality requires evidence or review.",
        ),
        _evaluate_contrast,
    ),
    (
        _definition(
            "LMPC-R9-B",
            "Declaration language requirements",
            "Declarations must be made in the language(s) the rules require; "
            "the requirement text is pending verification against the PDF.",
        ),
        _evaluate_language,
    ),
]
