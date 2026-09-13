"""LabelGuard AI Computer Vision service — Phase 1 skeleton."""
from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="LabelGuard AI Computer Vision",
    version="0.1.0",
    description="Label OCR and region detection. Implementation begins in Phase 2.",
)

app.include_router(health.router)
