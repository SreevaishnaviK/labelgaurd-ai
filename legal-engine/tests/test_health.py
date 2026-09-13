"""Legal Engine tests."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "LabelGuard AI Legal Engine"}


def test_evaluate_placeholder() -> None:
    response = client.post("/api/v1/evaluate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_implemented"
    assert "Phase 5" in body["message"]
