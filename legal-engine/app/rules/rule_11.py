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
from app.rules.schedule_data import mpe_for, third_schedule_flag
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


_MPE_RULE = RuleDefinition(
    rule_id="LMPC-R11-B",
    rule_number="11",
    title="Declared quantity within maximum permissible error",
    description="The measured quantity must be within the First Schedule "
    "maximum permissible error for the declared quantity. Runs only when a "
    "real physical measurement was supplied — an unmeasured package is "
    "never failed by inference.",
    source_page=72,
    applicability=[Applicability.RETAIL],
    required_fields=["net_quantity", "quantity_unit", "measured_quantity"],
    severity=Severity.MANDATORY,
    evaluation_type=EvaluationType.THRESHOLD,
)


def _evaluate_mpe(data: EvaluationInput) -> RuleResult:
    declared = data.product.net_quantity
    measured = data.visual_evidence.measured_quantity
    unit = data.product.quantity_unit
    if declared is None or unit is None:
        return support.not_verifiable(
            _MPE_RULE,
            "No declared net quantity is available, so no permissible-error "
            "comparison is possible.",
        )
    if measured is None:
        return support.result(
            _MPE_RULE,
            "REVIEW_REQUIRED",
            "The declared quantity exists but no physical measurement was "
            "supplied; the permissible-error check requires measuring the "
            "package. Requires review.",
            actual={"net_quantity": declared, "quantity_unit": unit},
            officer_verification=True,
        )
    band = mpe_for(declared, unit)
    if band is None:
        return support.not_verifiable(
            _MPE_RULE,
            "No verified First Schedule error row covers this declared "
            "quantity and unit; no deterministic conclusion is possible.",
            actual={"net_quantity": declared, "quantity_unit": unit},
            officer_verification=True,
        )
    if band.mpe_fraction is not None:
        tolerance = band.mpe_fraction * declared
        basis = f"{band.mpe_fraction:.1%} of the declared quantity"
    else:
        tolerance = float(band.mpe_absolute or 0.0)
        basis = f"{band.mpe_absolute:g} {band.unit} absolute"
    shortfall = declared - measured
    actual = {
        "net_quantity": declared,
        "measured_quantity": measured,
        "tolerance": round(tolerance, 4),
        "tolerance_basis": basis,
        "source_page": band.source_page,
    }
    if shortfall <= tolerance:
        return support.result(
            _MPE_RULE,
            "COMPLIANT",
            f"Measured quantity is within the permissible error ({basis}).",
            actual=actual,
        )
    return support.result(
        _MPE_RULE,
        "VIOLATION",
        f"Measured quantity is short by more than the permissible error "
        f"({basis}).",
        actual=actual,
    )


RULE_11_RULES = [(_RULE, _evaluate), (_MPE_RULE, _evaluate_mpe)]
