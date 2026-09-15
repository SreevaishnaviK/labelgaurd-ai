"""Rule 7 — principal display panel, size and lettering.

Machine-checkable scope this phase:
- LMPC-R7-A: principal display panel detection (structural evidence).
- LMPC-R7-B: minimum numeral height for the net-quantity declaration.
  Thresholds come from the Rule 7 tables in app/rules/schedule_data.py:
  Table I bands by net quantity declared by weight/volume (g/ml); Table II
  bands by principal-display-panel area (cm²) for quantities declared by
  length/area/number. Each table carries a normal-container column and a
  blown/formed/moulded/embossed/perforated column, selected by
  package.is_formed_container. A comparison runs ONLY on verified table rows
  plus a supplied measurement — anything less is NOT_VERIFIABLE or
  REVIEW_REQUIRED, never a guess.

Measured heights are in millimetres and refer to the numerals of the
net-quantity declaration (visual_evidence.estimated_letter_heights_mm).
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

_UNIT_KINDS_BY_TABLE = {
    # quantity units evaluated against Table I (weight/volume bands)
    "weight_volume": {"mg", "g", "kg", "t", "ml", "cl", "l"},
    # quantity units evaluated against Table II (PDP-area bands)
    "length_area_number": {"mm", "cm", "m", "km", "mm2", "cm2", "m2", "n", "no", "pcs", "units"},
}


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
            "Minimum height of numerals (net quantity declaration)",
            "Numerals in the net-quantity declaration must meet the minimum "
            "height for the package's net quantity category (Rule 7 tables).",
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


def _measured_height(data: EvaluationInput) -> float | None:
    heights = data.visual_evidence.estimated_letter_heights_mm
    return heights.get("net_quantity")


def _evaluate_letter_height(data: EvaluationInput) -> RuleResult:
    rule = RULE_7_RULES[1][0]
    measured = _measured_height(data)
    if measured is None:
        return support.not_verifiable(
            rule,
            "No letter-height measurement for the net-quantity declaration "
            "was supplied; the minimum-height check cannot run.",
        )
    if data.package.is_formed_container is None:
        return support.result(
            rule,
            "REVIEW_REQUIRED",
            "Letter height was measured but the container type (normal vs "
            "blown/formed/moulded/embossed/perforated) is unknown, which "
            "determines the applicable minimum. Requires review.",
            actual={"measured_height_mm": measured},
            officer_verification=True,
        )

    unit = data.product.quantity_unit
    kind = (unit or "").strip().lower()
    if kind in _UNIT_KINDS_BY_TABLE["weight_volume"]:
        by_pdp_area = False
        band_basis = "net quantity (weight/volume)"
    elif kind in _UNIT_KINDS_BY_TABLE["length_area_number"]:
        by_pdp_area = True
        band_basis = "principal display panel area"
    else:
        return support.result(
            rule,
            "REVIEW_REQUIRED",
            f"Quantity unit {unit!r} is unrecognized, so the applicable "
            "height table (weight/volume vs length/area/number) cannot be "
            "selected. Requires review.",
            actual={"measured_height_mm": measured, "quantity_unit": unit},
            officer_verification=True,
        )
    table = letter_height_table(data.package.is_formed_container, by_pdp_area=by_pdp_area)
    if not table.verified:
        return support.not_verifiable(
            rule,
            "The applicable minimum-height table has not been verified "
            "against the supplied PDF, so no threshold comparison is "
            "performed.",
            officer_verification=True,
        )

    declared = data.product.net_quantity
    if by_pdp_area:
        # Table II bands are keyed by principal-display-panel area (cm²).
        band_key = data.visual_evidence.principal_display_panel_area_cm2
        if band_key is None:
            return support.not_verifiable(
                rule,
                "Net quantity is declared by length/area/number, so the "
                "height band depends on the principal-display-panel area, "
                "which was not supplied.",
                actual={"measured_height_mm": measured},
            )
        key_label = "pdp_area_cm2"
    else:
        # Table I bands are keyed by the declared net quantity (g/ml).
        if declared is None:
            return support.not_verifiable(
                rule,
                "No net quantity value was extracted, so the height band "
                "cannot be selected.",
                actual={"measured_height_mm": measured},
            )
        band_key = declared
        key_label = "net_quantity"

    band = next(
        (r for r in table.rows
         if (r.min_quantity is None or band_key >= r.min_quantity)
         and (r.max_quantity is None or band_key <= r.max_quantity)),
        None,
    )
    if band is None:
        return support.not_verifiable(
            rule,
            "The package falls outside every verified height band; no "
            "deterministic conclusion is possible.",
            actual={"measured_height_mm": measured, key_label: band_key},
            officer_verification=True,
        )

    actual = {
        "measured_height_mm": measured,
        "minimum_height_mm": band.min_height_mm,
        "net_quantity": declared,
        "band": {"min": band.min_quantity, "max": band.max_quantity},
        "band_basis": band_basis,
        "container": "formed" if data.package.is_formed_container else "normal",
    }
    if by_pdp_area:
        actual["pdp_area_cm2"] = band_key
    if measured >= band.min_height_mm:
        return support.result(
            rule,
            "COMPLIANT",
            f"Numeral height {measured} mm meets the {band.min_height_mm} mm "
            f"minimum for this package category.",
            actual=actual,
        )
    return support.result(
        rule,
        "VIOLATION",
        f"Numeral height {measured} mm is below the {band.min_height_mm} mm "
        f"minimum for this package category "
        f"({band_basis}, {'formed' if data.package.is_formed_container else 'normal'} container).",
        actual=actual,
    )
