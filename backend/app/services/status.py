"""Aggregated system status.

Checks PostgreSQL and the three internal services. Any unreachable
dependency is reported as "unavailable" — this endpoint never raises.

Phase 4: ai_provider exposes the AI service's configured provider NAME only
("none" | "mock" | "openai"; "unknown" when the AI service is unreachable).
No keys or credential-bearing values ever pass through here.
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


def _ping_with_provider(url: str) -> tuple[str, str]:
    """Health status plus the service's provider name (name only, no secrets)."""
    try:
        response = httpx.get(f"{url}/health", timeout=_TIMEOUT_SECONDS)
        if response.status_code == 200:
            try:
                provider = response.json().get("provider")
            except ValueError:
                provider = None
            return "ok", provider or "none"
        return "unavailable", "unknown"
    except httpx.HTTPError:
        return "unavailable", "unknown"


def get_system_status() -> dict:
    settings = get_settings()
    ai_status, ai_provider = _ping_with_provider(settings.ai_service_url)
    return {
        "backend": "ok",
        "database": "ok" if check_database_connection() else "unavailable",
        "computer_vision": _ping(settings.cv_service_url),
        "ai": ai_status,
        "legal_engine": _ping(settings.legal_engine_url),
        "ai_provider": ai_provider,
    }
