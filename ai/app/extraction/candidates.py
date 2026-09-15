"""Deterministic results → candidate payload for AI interpretation.

The AI sees every deterministic field (including not_detected ones) so it
can also report values the rules missed entirely; gating decides only
whether a provider call happens at all.
"""
from app.schemas.extraction import (
    CandidateField,
    CandidateReading,
    ExtractedFieldOut,
)


def build_candidates(fields: list[ExtractedFieldOut]) -> list[CandidateField]:
    return [
        CandidateField(
            field_name=f.field_name,
            status=f.status,
            value=f.value,
            extraction_confidence=f.extraction_confidence,
            readings=[
                CandidateReading(
                    raw_text=c.raw_text,
                    value=c.value,
                    method="deterministic",
                    confidence=f.extraction_confidence,
                    evidence=list(c.evidence),
                )
                for c in (f.candidates or [])
            ],
        )
        for f in fields
    ]
