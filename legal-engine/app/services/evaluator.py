"""Evaluation service: discovers enabled rules from the registry and runs
each evaluator against the input. No rule-specific branching lives here —
adding a rule means registering it, nothing else.

Every result is returned exactly as produced (the automated result is
immutable; any future officer override is stored separately, never spliced
into these objects).
"""
from app.rules.registry import RULE_REGISTRY
from app.schemas.evaluation import EvaluationInput, RuleResultOut


def evaluate(data: EvaluationInput) -> list[RuleResultOut]:
    results = []
    for rule, evaluator in RULE_REGISTRY:
        if not rule.enabled:
            continue
        result = evaluator(data)
        results.append(RuleResultOut(**result.model_dump()))
    return results
