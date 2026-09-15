"""Rule data model and evaluation states.

Every rule is data (RuleDefinition); every evaluator returns exactly one
EvaluationState per rule with a fully traceable RuleResult. The engine never
converts missing information into a violation: absence is a VIOLATION only
when the supplied evidence establishes the declaration is actually absent
(visual_evidence.label_fully_processed), otherwise NOT_VERIFIABLE.

Source-of-law discipline: source_document is a constant (the supplied PDF);
source_page stays None unless verified against that PDF. No legal value is
hard-coded from general knowledge.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.evaluation import Applicability


SOURCE_DOCUMENT = "Legal Metrology (Packaged Commodities) Rules, 2011"


class EvaluationState(str, Enum):
    COMPLIANT = "COMPLIANT"
    VIOLATION = "VIOLATION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(str, Enum):
    MANDATORY = "mandatory"
    QUALIFICATORY = "qualificatory"


class EvaluationType(str, Enum):
    PRESENCE = "presence"
    THRESHOLD = "threshold"
    FORMAT = "format"
    PLACEMENT = "placement"
    DATA_COMPARISON = "data_comparison"


class RuleDefinition(BaseModel):
    """One machine-checkable provision, fully sourced."""

    rule_id: str
    rule_number: str
    title: str
    description: str
    source_document: str = SOURCE_DOCUMENT
    # None until verified against the supplied PDF — never a guess.
    source_page: int | None = None
    applicability: list[Applicability] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    severity: Severity = Severity.MANDATORY
    evaluation_type: EvaluationType
    # For presence rules with alternative fields: True means ANY one required
    # field satisfies the rule (e.g. manufacturer OR packer OR importer);
    # False means every required field must be present.
    any_of: bool = False
    enabled: bool = True


class RuleResult(BaseModel):
    """Standard, immutable evaluation result for one rule."""

    rule_id: str
    rule_number: str
    title: str
    status: EvaluationState
    severity: Severity
    finding: str
    required_information: list[str] = Field(default_factory=list)
    actual_information: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Any] = Field(default_factory=list)
    confidence: float | None = None
    source: dict[str, Any]
    requires_officer_verification: bool = False
