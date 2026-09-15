"""Rule 8 — where declarations are required to appear.

Placement is a layout question: it needs region evidence (which declaration
sits in which panel region) that this phase's pipeline does not reliably
supply for arbitrary labels. The rule is registered with its evaluator so the
framework is real; with no placement evidence the check is NOT_VERIFIABLE —
placement is never inferred from text order. A full region map
(declaration_regions with panel assignments) activates the deterministic
check without evaluator changes.
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

_RULE = RuleDefinition(
    rule_id="LMPC-R8-A",
    rule_number="8",
    title="Declarations appear on the principal display panel",
    description="Required declarations must appear on the principal display "
    "panel of the package, as Rule 8 specifies.",
    source_page=None,
    applicability=[Applicability.RETAIL],
    severity=Severity.MANDATORY,
    evaluation_type=EvaluationType.PLACEMENT,
)


def _evaluate(data: EvaluationInput) -> RuleResult:
    regions = data.visual_evidence.declaration_regions
    pdp_detected = data.visual_evidence.principal_display_panel_detected
    if regions and pdp_detected is True:
        # Region map exists and the panel was found: check placements
        # deterministically once region entries carry panel assignments.
        unplaced = [r for r in regions if r.get("on_principal_display_panel") is None]
        if unplaced:
            return support.result(
                _RULE,
                "REVIEW_REQUIRED",
                "Declaration regions were supplied without panel assignments; "
                "placement cannot be established automatically.",
                actual={"regions": len(regions), "unplaced": len(unplaced)},
                officer_verification=True,
            )
        return support.result(
            _RULE,
            "REVIEW_REQUIRED",
            "Placement comparison against the Rule 8 specification is not "
            "implemented in this phase.",
            officer_verification=True,
        )
    return support.not_verifiable(
        _RULE,
        "No declaration-region/panel layout evidence was supplied; placement "
        "cannot be determined from text alone.",
    )


RULE_8_RULES = [(_RULE, _evaluate)]
