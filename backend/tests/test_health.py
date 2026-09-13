"""Tests for health endpoints."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "LabelGuard AI Backend"


def test_system_status_never_crashes() -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == "ok"
    for key in ("database", "computer_vision", "ai", "legal_engine"):
        assert body[key] in ("ok", "unavailable")
