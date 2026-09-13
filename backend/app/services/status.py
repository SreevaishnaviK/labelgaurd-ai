"""Aggregated system status.

Checks PostgreSQL and the three internal services. Any unreachable
dependency is reported as "unavailable" — this endpoint never raises.
"""
import httpx

from app.config import get_settings
from app.database import check_database_connection

_TIMEOUT_SECONDS = 2.0


def _ping(url: str) -> str:
    try:
        response = httpx.get(f"{url}/health", timeout=_TIMEOUT_SECONDS)
        return "ok" if response.status_code == 200 else "unavailable"
    except httpx.HTTPError:
        return "unavailable"


def get_system_status() -> dict:
    settings = get_settings()
    return {
        "backend": "ok",
        "database": "ok" if check_database_connection() else "unavailable",
        "computer_vision": _ping(settings.cv_service_url),
        "ai": _ping(settings.ai_service_url),
        "legal_engine": _ping(settings.legal_engine_url),
    }
