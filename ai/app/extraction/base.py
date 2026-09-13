"""Field extractor abstraction.

DeterministicFieldExtractor ships today; a future LLMFieldExtractor can
implement the same contract without changing the API or backend contract.
"""
from abc import ABC, abstractmethod

from app.schemas.extraction import ExtractedFieldOut, OCRPageIn


class BaseFieldExtractor(ABC):
    """Contract: OCR pages in, structured fields out. No legal judgment."""

    name: str = "base"

    @abstractmethod
    def extract_fields(self, pages: list[OCRPageIn]) -> list[ExtractedFieldOut]:
        """Return one ExtractedFieldOut per known field, always the full set."""
