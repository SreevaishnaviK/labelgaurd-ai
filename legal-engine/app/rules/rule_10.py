"""Rule 10 — name and address of manufacturer / packer / importer.

Structured validation of who must be declared and what the declaration must
contain. An incomplete OCR extraction is NOT a violation: party naming and
address completeness are judged from supplied fields, with the shared
evidence policy deciding whether absence is established.

Checks:
- LMPC-R10-A: a responsible party is named (manufacturer, packer, or importer).
- LMPC-R10-B: for imported packages, the importer is the declared party.
- LMPC-R10-C: an address accompanies the declared party.
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


def _definition(rule_id: str, title: str, description: str, fields: list[str], applicability: list[Applicability]) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        rule_number="10",
        title=title,
        description=description,
        source_page=None,
        applicability=applicability,
        required_fields=fields,
        severity=Severity.MANDATORY,
        evaluation_type=EvaluationType.PRESENCE,
    )


def _evaluate_party(data: EvaluationInput) -> RuleResult:
    rule = RULE_10_RULES[0][0]
    parties = {
        name: value
        for name in ("manufacturer", "packer", "importer")
        if (value := getattr(data.product, name, None)) is not None
    }
    if parties:
        return support.result(
            rule,
            "COMPLIANT",
            "Responsible party declared: " + ", ".join(sorted(parties)) + ".",
            actual=parties,
        )
    if support.absence_is_established(data):
        return support.result(
            rule,
            "VIOLATION",
            "No manufacturer, packer, or importer name appears on the "
            "fully-processed label evidence.",
        )
    return support.result(
        rule,
        "NOT_VERIFIABLE",
        "No party name was extracted; the evidence does not establish whether "
        "one is declared on the package.",
        officer_verification=True,
    )


def _evaluate_importer(data: EvaluationInput) -> RuleResult:
    rule = RULE_10_RULES[1][0]
    if not data.package.is_imported:
        return support.not_applicable(rule, "Package is not declared as imported.")
    if data.product.importer is not None:
        return support.result(
            rule,
            "COMPLIANT",
            "Importer is declared on the imported package.",
            actual={"importer": data.product.importer},
        )
    if support.absence_is_established(data):
        return support.result(
            rule,
            "VIOLATION",
            "Imported package shows no importer declaration on the "
            "fully-processed label evidence.",
        )
    return support.result(
        rule,
        "NOT_VERIFIABLE",
        "Package is marked imported but no importer name was extracted; "
        "absence is not established by the evidence.",
        officer_verification=True,
    )


def _evaluate_address(data: EvaluationInput) -> RuleResult:
    rule = RULE_10_RULES[2][0]
    addresses = {
        name: value
        for name in ("address", "manufacturer_address", "packer_address", "importer_address")
        if (value := getattr(data.product, name, None)) is not None
    }
    parties = {
        name
        for name in ("manufacturer", "packer", "importer")
        if getattr(data.product, name, None) is not None
    }
    if addresses and parties:
        return support.result(
            rule,
            "COMPLIANT",
            "Address information accompanies the declared party.",
            actual=addresses,
        )
    if not parties:
        return support.not_verifiable(
            rule,
            "No responsible party was extracted, so the corresponding address "
            "requirement cannot be assessed.",
            officer_verification=True,
        )
    if support.absence_is_established(data):
        return support.result(
            rule,
            "VIOLATION",
            "A party is declared but no address appears anywhere on the "
            "fully-processed label evidence.",
            actual={"parties": sorted(parties)},
        )
    return support.result(
        rule,
        "NOT_VERIFIABLE",
        "A party is declared but no address was extracted; the evidence does "
        "not establish that the address is missing from the package.",
        actual={"parties": sorted(parties)},
        officer_verification=True,
    )


RULE_10_RULES = [
    (
        _definition(
            "LMPC-R10-A",
            "Responsible party named",
            "The package must declare the actual corporate or business name of "
            "the manufacturer, packer, or importer, as applicable.",
            ["manufacturer", "packer", "importer"],
            [Applicability.RETAIL],
        ),
        _evaluate_party,
    ),
    (
        _definition(
            "LMPC-R10-B",
            "Importer declared on imported packages",
            "Where a package is imported, the importer's name must be the "
            "declared party.",
            ["importer"],
            [Applicability.IMPORT],
        ),
        _evaluate_importer,
    ),
    (
        _definition(
            "LMPC-R10-C",
            "Address of the declared party",
            "The declaration must include the address of the named "
            "manufacturer, packer, or importer.",
            ["address", "manufacturer_address", "packer_address", "importer_address"],
            [Applicability.RETAIL],
        ),
        _evaluate_address,
    ),
]
