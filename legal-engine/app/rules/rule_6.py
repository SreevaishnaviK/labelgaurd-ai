"""Rule 6 — mandatory declarations on retail packages (presence checks).

Machine-checkable scope for this phase: does the structured input contain
each required declaration? Manner/placement of the declarations belongs to
Rules 8–12. Sub-clause numbering beyond 6(1)(a) is left unnumbered until
verified against the supplied PDF; the declarations themselves (name and
address of manufacturer/packer/importer, common/generic name, net quantity,
month-year of manufacture/pre-packing/import, retail sale price, consumer-care
contact) are exactly the six the project spec lists for Rule 6.

States: a present declaration is COMPLIANT; a declaration the evidence
establishes as absent is VIOLATION; missing without that affirmation is
NOT_VERIFIABLE — never an automatic violation.
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


def _definition(rule_id: str, rule_number: str, title: str, fields: list[str], description: str, any_of: bool = False) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        rule_number=rule_number,
        title=title,
        description=description,
        source_page=None,  # filled only after verification against the supplied PDF
        applicability=[Applicability.RETAIL],
        required_fields=fields,
        severity=Severity.MANDATORY,
        evaluation_type=EvaluationType.PRESENCE,
        any_of=any_of,
    )


def _presence_check(rule: RuleDefinition, data: EvaluationInput) -> RuleResult:
    """One required-field presence check with the shared evidence policy."""
    present = {
        field: value
        for field in rule.required_fields
        if (value := getattr(data.product, field, None)) is not None
    }
    satisfied = any(present.values()) if rule.any_of else len(present) == len(rule.required_fields)
    if satisfied:
        return support.result(
            rule,
            "COMPLIANT",
            "Required declaration is present in the supplied information.",
            actual=present,
        )
    missing = [f for f in rule.required_fields if f not in present]
    if support.absence_is_established(data):
        return support.result(
            rule,
            "VIOLATION",
            f"Declaration absent: {', '.join(missing)} does not appear "
            "anywhere on the fully-processed label evidence.",
            actual=present,
        )
    return support.result(
        rule,
        "NOT_VERIFIABLE",
        f"Not extracted: {', '.join(missing)}. The evidence does not establish "
        "whether the declaration is present on the package, so compliance "
        "cannot be determined automatically.",
        actual=present,
        officer_verification=True,
    )


def _retail_rule(
    rule_id: str,
    rule_number: str,
    title: str,
    fields: list[str],
    description: str,
    any_of: bool = False,
) -> tuple[RuleDefinition, object]:
    """Pair a definition with its presence evaluator (registry contract)."""
    rule = _definition(rule_id, rule_number, title, fields, description, any_of=any_of)
    return rule, (lambda data: _presence_check(rule, data))


RULE_6_RULES = [
    _retail_rule(
        "LMPC-R6-A",
        "6(1)(a)",
        "Manufacturer/Packer/Importer declaration",
        ["manufacturer", "packer", "importer"],
        "The package must declare the name of the manufacturer, packer, or "
        "importer, as applicable. Any one of the three satisfies this check; "
        "which party must be named for a specific package is assessed by "
        "Rule 10.",
        any_of=True,
    ),
    _retail_rule(
        "LMPC-R6-B",
        "6(1)",
        "Common or generic name of the commodity",
        ["product_name"],
        "The package must declare the common or generic name of the commodity "
        "contained.",
    ),
    _retail_rule(
        "LMPC-R6-C",
        "6(1)",
        "Net quantity declaration",
        ["net_quantity"],
        "The package must declare the net quantity of the commodity "
        "(see Rules 11–12 for manner and units).",
    ),
    _retail_rule(
        "LMPC-R6-D",
        "6(1)",
        "Month and year of manufacture/pre-packing/import",
        ["manufacture_month", "manufacture_year"],
        "The package must declare the month and year in which the commodity "
        "was manufactured, pre-packed, or imported.",
    ),
    _retail_rule(
        "LMPC-R6-E",
        "6(1)",
        "Retail sale price (MRP)",
        ["mrp"],
        "The package must declare the retail sale price, inclusive of all "
        "taxes.",
    ),
    _retail_rule(
        "LMPC-R6-F",
        "6(1)",
        "Consumer-care contact information",
        ["consumer_care", "customer_care_phone", "customer_care_email"],
        "The package must carry consumer-care contact details. Any one of the "
        "supported contact forms satisfies this check.",
        any_of=True,
    ),
]
