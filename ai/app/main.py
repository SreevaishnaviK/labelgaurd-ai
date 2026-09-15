"""LabelGuard AI AI Service — Phase 4: AI-assisted extraction.

Receives OCR output (never images) and returns structured product fields
with evidence references. Deterministic rules always run first; an optional
AI provider (AI_PROVIDER=none|mock|openai) interprets ambiguous or weak
results behind the same API. This service never makes legal or compliance
judgments.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import get_settings

app = FastAPI(
    title="LabelGuard AI AI Service",
    version="0.3.0",
    description="Deterministic + AI-assisted field extraction over OCR output (Phase 4).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().__dict__.get("cors_origins", ["*"]) or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
