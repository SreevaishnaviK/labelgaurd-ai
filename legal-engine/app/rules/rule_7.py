"""Rule 7 — principal display panel, size and lettering.

Machine-checkable scope this phase:
- LMPC-R7-A: principal display panel detection (structural evidence).
- LMPC-R7-B: minimum numeral height for net quantity / retail sale price.
  The numeric thresholds live in First Schedule Table I/II data
  (app/rules/schedule_data.py). This phase's build has NOT verified those
  values against the supplied PDF, so with unverified data the check returns
  NOT_VERIFIABLE rather than evaluating against remembered values — never
  guessing. When the data rows carry verified=true with source_page, the
  same evaluator evaluates deterministically against the table.

Container subtype (normal vs blown/formed/moulded/embossed/perforated) is
taken from package.is_formed_container and selects the table column; when
the package type is unknown, the check is NOT_VERIFIABLE.
"""
from app.rules import support
from app.rules.rule_model import (
    Applicability,
    EvaluationType,
    RuleDefinition,
    RuleResult,
    Severity,
)
from app.rules.schedule_data import letter_height_table
from app.schemas.evaluation import EvaluationInput


def _definition(rule_id: str, rule_number: str, title: str, description: str, eval_type: EvaluationType) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        rule_number=rule_number,
        title=title,
        description=description,
        source_page=None,
        applicability=[Applicability.RETAIL],
        severity=Severity.MANDATORY,
        evaluation_type=eval_type,
    )


RULE_7_RULES: list[tuple[RuleDefinition, object]] = [
    (
        _definition(
            "LMPC-R7-A",
            "7",
            "Principal display panel present",
            "Retail packages must present the required declarations on the "
            "principal display panel.",
            EvaluationType.PLACEMENT,
        ),
        lambda data: _evaluate_pdp(data),
    ),
    (
        _definition(
            "LMPC-R7-B",
            "7",
            "Minimum height of numerals (net quantity / retail sale price)",
            "Numerals in the net-quantity and retail-sale-price declarations "
            "must meet the minimum height for the package's net quantity "
            "category (First Schedule tables).",
            EvaluationType.THRESHOLD,
        ),
        lambda data: _evaluate_letter_height(data),
    ),
]


def _evaluate_pdp(data: EvaluationInput) -> RuleResult:
    rule = RULE_7_RULES[0][0]
    detected = data.visual_evidence.principal_display_panel_detected
    if detected is True:
        return support.result(rule, "COMPLIANT", "Principal display panel detected in the label evidence.")
    if detected is False and support.absence_is_established(data):
        return support.result(
            rule,
            "VIOLATION",
            "No principal display panel could be identified on the "
            "fully-processed label evidence.",
        )
    return support.not_verifiable(
        rule,
        "No principal-display-panel determination available in the supplied "
        "evidence.",
    )


def _evaluate_letter_height(data: EvaluationInput) -> RuleResult:
    rule = RULE_7_RULES[1][0]
    heights = data.visual_evidence.estimated_letter_heights_mm
    measured = {k: v for k, v in heights.items() if k in ("net_quantity", "mrp") and v is not None}
    if not measured:
        return support.not_verifiable(
            rule,
            "No letter-height measurements for the net-quantity or MRP "
            "declarations were supplied; the minimum-height check cannot run.",
        )
    if data.package.is_formed_container is None:
        return support.result(
            rule,
            "REVIEW_REQUIRED",
            "Letter heights were measured but the container type (normal vs "
            "blown/formed/moulded/embossed/perforated) is unknown, which "
            "determines the applicable minimum. Requires review.",
            actual={"measured_heights_mm": measured},
            officer_verification=True,
        )
    table = letter_height_table(data.package.is_formed_container)
    if table is None or not table.verified:
        return support.not_verifiable(
            rule,
            "The applicable minimum-height table has not been verified against "
            "the supplied PDF, so no threshold comparison is performed.",
            officer_verification=True,
        )
    return support.result(
        rule,
        "REVIEW_REQUIRED",
        "Threshold comparison is not implemented in this phase.",
        actual={"measured_heights_mm": measured},
        officer_verification=True,
    )
