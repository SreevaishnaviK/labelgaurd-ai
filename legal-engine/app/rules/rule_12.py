"""Rule 12 — manner of declaring quantity: unit-kind framework.

Deterministic unit-kind checks only: mass, length, area, volume, or number
must match what the commodity kind implies. The commodity-specific
exceptions (Fourth Schedule, exceptions to Rule 12(2)) are data rows in
schedule_data.fourth_schedule_flag() — verified rows only; nothing is
inferred from general knowledge. Unit spelling/symbol validation is Rule 13.
"""
from app.rules import support
from app.rules.rule_model import (
    Applicability,
    EvaluationType,
    RuleDefinition,
    RuleResult,
    Severity,
)
from app.rules.schedule_data import fourth_schedule_flag
from app.schemas.evaluation import EvaluationInput

_UNIT_KINDS: dict[str, str] = {
    # mass
    "mg": "mass", "g": "mass", "kg": "mass", "t": "mass",
    # length
    "mm": "length", "cm": "length", "m": "length", "km": "length",
    # area
    "mm2": "area", "cm2": "area", "m2": "area",
    # volume
    "ml": "volume", "cl": "volume", "l": "volume",
    # number
    "n": "number", "no": "number", "pcs": "number", "units": "number",
}


def unit_kind(unit: str | None) -> str | None:
    """The measurement kind of a declared unit symbol (None = unrecognized)."""
    if not unit:
        return None
    return _UNIT_KINDS.get(unit.strip().lower())


_RULE = RuleDefinition(
    rule_id="LMPC-R12-A",
    rule_number="12",
    title="Quantity declared in the proper unit kind",
    description="The net quantity must be declared in the unit kind the "
    "rules prescribe for the commodity (mass, length, area, volume, or "
    "number), subject to the Fourth Schedule exceptions.",
    source_page=None,
    applicability=[Applicability.RETAIL],
    required_fields=["net_quantity", "quantity_unit"],
    severity=Severity.MANDATORY,
    evaluation_type=EvaluationType.FORMAT,
)


def _evaluate(data: EvaluationInput) -> RuleResult:
    unit = data.product.quantity_unit
    category = data.package.commodity_category
    if unit is None:
        if data.product.net_quantity is None:
            return support.not_verifiable(
                _RULE,
                "No quantity declaration was extracted, so the unit cannot be "
                "assessed.",
                officer_verification=True,
            )
        if support.absence_is_established(data):
            return support.result(
                _RULE,
                "VIOLATION",
                "A quantity is expressed on the fully-processed label but no "
                "unit appears with it.",
            )
        return support.result(
            _RULE,
            "NOT_VERIFIABLE",
            "Quantity value was extracted without a recognizable unit; the "
            "evidence does not establish that no unit is declared.",
            actual={"net_quantity": data.product.net_quantity},
            officer_verification=True,
        )
    kind = unit_kind(unit)
    if kind is None:
        # Unknown symbol: not in the unit table. Whether it is legally
        # permissible depends on the schedule text — not decidable here.
        return support.result(
            _RULE,
            "REVIEW_REQUIRED",
            f"Unit symbol {unit!r} is not in the recognized unit-kind table; "
            "its permissibility requires review against the rules.",
            actual={"quantity_unit": unit},
            officer_verification=True,
        )
    exception = fourth_schedule_flag(category) if category else None
    if exception is not None:
        return support.result(
            _RULE,
            "REVIEW_REQUIRED",
            "Commodity has a Fourth Schedule exception entry; the exception "
            "text must be applied by review in this phase.",
            actual={"quantity_unit": unit, "exception": exception.detail},
            officer_verification=True,
        )
    return support.result(
        _RULE,
        "COMPLIANT",
        f"Quantity is declared in a recognized {kind} unit.",
        actual={"quantity_unit": unit, "unit_kind": kind},
    )


RULE_12_RULES = [(_RULE, _evaluate)]
