"""LabelGuard AI AI Service — Phase 1 skeleton."""
from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="LabelGuard AI AI Service",
    version="0.1.0",
    description="Field extraction and assessment. Implementation begins in Phase 4.",
)

app.include_router(health.router)
