"""Rule 11 — general provisions relating to declaration of quantity.

Framework scope this phase:
- The net quantity declaration must exist (presence, shared evidence policy).
- The "wrapper/material weight" concept and "when packed" applicability are
  represented structurally: which commodities may use "when packed" comes
  from the Third Schedule data (verified rows only) — no remembered lists.
Physical weighing is explicitly out of scope for this phase.
"""
from app.rules import support
from app.rules.rule_model import (
    Applicability,
    EvaluationType,
    RuleDefinition,
    RuleResult,
    Severity,
)
from app.rules.schedule_data import third_schedule_flag
from app.schemas.evaluation import EvaluationInput

_RULE = RuleDefinition(
    rule_id="LMPC-R11-A",
    rule_number="11",
    title="Net quantity declared (exclusive of wrapper/material)",
    description="The net quantity declaration must be present and must "
    "represent the quantity of the commodity, exclusive of the wrapper or "
    "container material. Which commodities may declare 'when packed' is "
    "determined from the Third Schedule.",
    source_page=None,
    applicability=[Applicability.RETAIL],
    required_fields=["net_quantity"],
    severity=Severity.MANDATORY,
    evaluation_type=EvaluationType.PRESENCE,
)


def _evaluate(data: EvaluationInput) -> RuleResult:
    net = data.product.net_quantity
    category = data.package.commodity_category
    if net is not None:
        when_packed = third_schedule_flag(category) if category else None
        if category and when_packed is None:
            return support.result(
                _RULE,
                "COMPLIANT",
                "Net quantity is declared. 'When packed' qualification: the "
                "commodity category is known but has no verified Third "
                "Schedule entry, so no allowance is applied.",
                actual={"net_quantity": net, "commodity_category": category},
            )
        return support.result(
            _RULE,
            "COMPLIANT",
            "Net quantity is declared.",
            actual={"net_quantity": net},
        )
    if support.absence_is_established(data):
        return support.result(
            _RULE,
            "VIOLATION",
            "No net quantity declaration appears on the fully-processed "
            "label evidence.",
        )
    return support.result(
        _RULE,
        "NOT_VERIFIABLE",
        "Net quantity was not extracted; the evidence does not establish "
        "whether it is declared on the package.",
        officer_verification=True,
    )


RULE_11_RULES = [(_RULE, _evaluate)]
