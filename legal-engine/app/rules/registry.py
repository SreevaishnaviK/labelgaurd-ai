"""Registry of machine-checkable LMPC 2011 rules.

Each entry pairs the immutable rule definition (RuleDefinition) with its
evaluator (a function input -> RuleResult). The evaluator service discovers
enabled rules here — there is no per-rule branching anywhere else.

Source pages stay None: they are filled only after verification against the
supplied PDF (docs/schedule-population.md). All evaluators currently operate
on structural/presence logic that does not depend on unverified values;
Schedule-dependent logic activates only when the data rows are verified.
"""
from collections.abc import Callable

from app.rules.rule_10 import RULE_10_RULES
from app.rules.rule_11 import RULE_11_RULES
from app.rules.rule_12 import RULE_12_RULES
from app.rules.rule_13 import RULE_13_RULES
from app.rules.rule_6 import RULE_6_RULES
from app.rules.rule_7 import RULE_7_RULES
from app.rules.rule_8 import RULE_8_RULES
from app.rules.rule_9 import RULE_9_RULES
from app.rules.rule_model import RuleDefinition, RuleResult
from app.schemas.evaluation import EvaluationInput

Evaluator = Callable[[EvaluationInput], RuleResult]

RULE_REGISTRY: list[tuple[RuleDefinition, Evaluator]] = [
    *RULE_6_RULES,
    *RULE_7_RULES,
    *RULE_8_RULES,
    *RULE_9_RULES,
    *RULE_10_RULES,
    *RULE_11_RULES,
    *RULE_12_RULES,
    *RULE_13_RULES,
]
