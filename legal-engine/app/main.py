"""LabelGuard AI Legal Engine — Phase 1 skeleton."""
from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="LabelGuard AI Legal Engine",
    version="0.1.0",
    description="Legal Metrology rule evaluation. Implementation begins in Phase 5.",
)

app.include_router(health.router)
