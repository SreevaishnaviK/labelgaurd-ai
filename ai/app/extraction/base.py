"""Field extractor abstraction.

DeterministicFieldExtractor ships today; a future LLMFieldExtractor can
implement the same contract without changing the API or backend contract.

FIELD_NAMES is the single source of truth for the stable field set: the
deterministic extractor emits exactly these, and AI fields outside the set
are rejected as hallucinations.
"""
from abc import ABC, abstractmethod

from app.schemas.extraction import ExtractedFieldOut, OCRPageIn

# The prompt's 23 fields + marketer ("Marketed by" is a listed role
# indicator). Order is the API's field order.
FIELD_NAMES: tuple[str, ...] = (
    "product_name", "manufacturer", "packer", "importer", "marketer",
    "manufacturer_address", "packer_address", "importer_address",
    "net_quantity", "mrp", "manufacturing_date", "packing_date",
    "best_before", "use_by", "expiry_date", "consumer_care",
    "customer_care_phone", "customer_care_email", "website",
    "batch_number","fssai_license_number", "lot_number", "country_of_origin", "ingredients",
    "vegetarian_non_vegetarian",
)


class BaseFieldExtractor(ABC):
    """Contract: OCR pages in, structured fields out. No legal judgment."""

    name: str = "base"

    @abstractmethod
    def extract_fields(self, pages: list[OCRPageIn]) -> list[ExtractedFieldOut]:
        """Return one ExtractedFieldOut per known field, always the full set."""
