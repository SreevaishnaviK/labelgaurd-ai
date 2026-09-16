"""Legal Engine health + version routes."""
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "LabelGuard AI Legal Engine",
        "version": get_settings().engine_version,
    }
