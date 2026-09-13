"""LabelGuard AI AI Service — Phase 3: structured field extraction.

Receives OCR output (never images) and returns structured product fields with
evidence references. Deterministic rules today; an LLM extractor can replace
the implementation behind the same API later. This service never makes legal
or compliance judgments.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import get_settings

app = FastAPI(
    title="LabelGuard AI AI Service",
    version="0.2.0",
    description="Deterministic field extraction over OCR output (Phase 3).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().__dict__.get("cors_origins", ["*"]) or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
