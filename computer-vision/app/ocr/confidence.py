"""Confidence aggregation computed strictly from actual OCR output."""


def average_confidence(confidences: list[float]) -> float:
    """Mean confidence across valid blocks, rounded to 1 decimal. 0.0 when empty."""
    if not confidences:
        return 0.0
    return round(sum(confidences) / len(confidences), 1)
