"""Legal Engine evaluation schemas.

The evaluation input mirrors what the CV/OCR/AI pipeline can supply about a
package. All fields are nullable: missing evidence is a first-class state,
never silently converted into a violation.
"""
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Applicability(str, Enum):
    """Rule scope tags used by evaluators to skip non-applicable rules."""

    PRE_RETAIL = "pre_retail"
    RETAIL = "retail"
    WHOLESALE = "wholesale"
    EXPORT = "export"
    IMPORT = "import"


class ProductInfo(BaseModel):
    """Structured fields as extracted by the CV/OCR/AI pipeline.

    None means "not extracted" — the engine decides whether that absence can
    be treated as established from the supplied evidence.
    """

    model_config = {"extra": "allow"}

    product_name: str | None = None
    manufacturer: str | None = None
    packer: str | None = None
    importer: str | None = None
    address: str | None = None
    manufacturer_address: str | None = None
    packer_address: str | None = None
    importer_address: str | None = None
    net_quantity: float | None = None
    quantity_unit: str | None = None
    mrp: dict[str, Any] | None = None
    manufacture_month: int | None = Field(default=None, ge=1, le=12)
    manufacture_year: int | None = None
    # Raw date declarations (extraction preserves them as text; date VALIDITY
    # is a legal question no engine rule performs).
    manufacturing_date: str | None = None
    packing_date: str | None = None
    best_before: str | None = None
    use_by: str | None = None
    expiry_date: str | None = None
    consumer_care: str | None = None
    customer_care_phone: str | None = None
    customer_care_email: str | None = None
    website: str | None = None
    ingredients: str | None = None
    country_of_origin: str | None = None
    batch_number: str | None = None
    lot_number: str | None = None
    vegetarian_non_vegetarian: str | None = None


class PackageInfo(BaseModel):
    model_config = {"extra": "allow"}

    package_type: str | None = None
    # Container formed by blowing/moulding etc. (affects Rule 7 lettering table).
    is_formed_container: bool | None = None
    is_imported: bool = False
    is_food: bool = False
    is_wholesale: bool = False
    is_export: bool = False
    # Category key into schedule data (e.g. "biscuits"); None = unclassified.
    commodity_category: str | None = None


class VisualEvidence(BaseModel):
    model_config = {"extra": "allow"}

    # True only when the pipeline affirms the whole label was captured and
    # read — the sole basis for treating a missing declaration as established.
    label_fully_processed: bool | None = None
    principal_display_panel_detected: bool | None = None
    # Area of the principal display panel in cm², when measured (selects the
    # Rule 7 Table II height band for quantities declared by length/area/number).
    principal_display_panel_area_cm2: float | None = None
    declaration_regions: list[dict[str, Any]] = Field(default_factory=list)
    text_regions: list[dict[str, Any]] = Field(default_factory=list)
    estimated_letter_heights_mm: dict[str, float] = Field(default_factory=dict)
    # Measured text/background contrast for a declaration region (0-21 scale),
    # when the CV pipeline provides it.
    contrast_ratio: float | None = None
    # Phase 7: per-region objective measurements from the CV evidence layer.
    # The engine reports them and applies only verified thresholds — never
    # invented ones.
    contrast_measurements: list[dict[str, Any]] = Field(default_factory=list)
    readability_measurements: list[dict[str, Any]] = Field(default_factory=list)
    # Language(s) the declarations were read in, when determined (e.g. "en").
    declaration_language: str | None = None
    # OCR evidence refs (block ids) supporting the structured fields.
    evidence_block_ids: list[str] = Field(default_factory=list)
    # Physically measured average quantity of the package in the same unit as
    # quantity_unit, when a real measurement was supplied. The engine NEVER
    # invents this: MPE checks run only when it is present.
    measured_quantity: float | None = None


class EvaluationInput(BaseModel):
    model_config = {"extra": "allow"}

    product: ProductInfo = Field(default_factory=ProductInfo)
    package: PackageInfo = Field(default_factory=PackageInfo)
    visual_evidence: VisualEvidence = Field(default_factory=VisualEvidence)


class RuleResultOut(BaseModel):
    """One rule's evaluation result (output of POST /api/v1/evaluate)."""

    rule_id: str
    rule_number: str
    title: str
    status: Literal["COMPLIANT", "VIOLATION", "REVIEW_REQUIRED", "NOT_VERIFIABLE", "NOT_APPLICABLE"]
    severity: Literal["mandatory", "qualificatory"]
    finding: str
    required_information: list[str] = Field(default_factory=list)
    actual_information: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Any] = Field(default_factory=list)
    confidence: float | None = None
    source: dict[str, Any]
    requires_officer_verification: bool = False


class EvaluateSuccess(BaseModel):
    status: Literal["success"]
    rules_evaluated: int
    results: list[RuleResultOut]
