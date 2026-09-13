"""Health and system status endpoints."""
from fastapi import APIRouter

import app.services.status as status_service

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "LabelGuard AI Backend"}


@router.get("/api/v1/system/status")
def system_status() -> dict:
    return status_service.get_system_status()
