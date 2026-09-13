"""Computer Vision service tests."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "LabelGuard AI Computer Vision"}


def test_analyze_requires_file() -> None:
    """Phase 2: the endpoint is real — it requires a multipart file."""
    response = client.post("/api/v1/analyze")
    assert response.status_code == 422
