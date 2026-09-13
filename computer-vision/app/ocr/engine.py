"""OCR engine abstraction.

Preprocessing is decoupled from OCR: any engine implementing BaseOCREngine
can be dropped in without touching the pipeline. Raw Tesseract word data is
returned so parsing stays engine-specific and testable.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import pytesseract


@dataclass
class RawWord:
    """A single OCR word with its geometry and engine confidence."""

    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    line_number: int
    block_number: int
    par_num: int = 0


@dataclass
class RawOCRResult:
    """Unparsed engine output for one page image."""

    words: list[RawWord] = field(default_factory=list)
    width: int = 0
    height: int = 0


class BaseOCREngine(ABC):
    """Contract for OCR engines. Implementations must be deterministic."""

    @abstractmethod
    def extract(self, image: np.ndarray) -> RawOCRResult:
        """Run OCR on a grayscale image matrix and return raw word data."""


def _clamp_confidence(value: float) -> float:
    """Clamp engine confidence to the valid 0–100 numeric range."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return -1.0  # invalid — filtered downstream
    if confidence != confidence:  # NaN
        return -1.0
    return max(0.0, min(100.0, confidence))


class TesseractOCREngine(BaseOCREngine):
    """Tesseract OCR via pytesseract, returning word-level geometry."""

    def extract(self, image: np.ndarray) -> RawOCRResult:
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            config="--psm 3",
        )
        height, width = image.shape[:2]
        words: list[RawWord] = []
        count = len(data["text"])
        for i in range(count):
            raw_conf = data["conf"][i]
            confidence = _clamp_confidence(raw_conf)
            text = (data["text"][i] or "").strip()
            if not text or confidence < 0:
                continue
            words.append(
                RawWord(
                    text=text,
                    confidence=confidence,
                    x=int(data["left"][i]),
                    y=int(data["top"][i]),
                    width=int(data["width"][i]),
                    height=int(data["height"][i]),
                    line_number=int(data["line_num"][i]),
                    block_number=int(data["block_num"][i]),
                    par_num=int(data["par_num"][i]),
                )
            )
        return RawOCRResult(words=words, width=width, height=height)


def get_ocr_engine(name: str) -> BaseOCREngine:
    """Resolve an OCR engine by config name (extensibility point)."""
    engines: dict[str, type[BaseOCREngine]] = {"tesseract": TesseractOCREngine}
    engine_cls = engines.get(name.lower())
    if engine_cls is None:
        raise ValueError(f"Unknown OCR engine: {name}")
    return engine_cls()
