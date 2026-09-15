"""Rule 13 — statement of units of weight, measure or number.

Checks whether the declared quantity uses an allowed unit representation,
based strictly on the engine's unit table. No fuzzy interpretation: an
unrecognized symbol is REVIEW_REQUIRED (an officer compares it with the
rule text), never an invented match.
"""
from app.rules import support
from app.rules.rule_model import (
    Applicability,
    EvaluationType,
    RuleDefinition,
    RuleResult,
    Severity,
)
from app.rules.rule_12 import unit_kind
from app.schemas.evaluation import EvaluationInput

_RULE = RuleDefinition(
    rule_id="LMPC-R13-A",
    rule_number="13",
    title="Unit symbol representation",
    description="The declaration of quantity must state the unit of weight, "
    "measure, or number in the prescribed manner. This check verifies the "
    "unit symbol against the engine's recognized-representation table.",
    source_page=None,
    applicability=[Applicability.RETAIL],
    required_fields=["quantity_unit"],
    severity=Severity.MANDATORY,
    evaluation_type=EvaluationType.FORMAT,
)


def _evaluate(data: EvaluationInput) -> RuleResult:
    unit = data.product.quantity_unit
    if unit is None:
        if data.product.net_quantity is None:
            return support.not_verifiable(
                _RULE, "No quantity declaration was extracted; no unit symbol to assess.",
                officer_verification=True,
            )
        return support.result(
            _RULE,
            "REVIEW_REQUIRED",
            "A quantity value was extracted without a unit symbol; whether "
            "the symbol is elsewhere on the label requires review.",
            officer_verification=True,
        )
    if unit_kind(unit) is None:
        return support.result(
            _RULE,
            "REVIEW_REQUIRED",
            f"Unit symbol {unit!r} is not a recognized representation; review "
            "against the rule text is required before any conclusion.",
            actual={"quantity_unit": unit},
            officer_verification=True,
        )
    return support.result(
        _RULE,
        "COMPLIANT",
        "Quantity uses a recognized unit representation.",
        actual={"quantity_unit": unit, "unit_kind": unit_kind(unit)},
    )


RULE_13_RULES = [(_RULE, _evaluate)]
