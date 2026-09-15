"""Legal Engine API tests: health and the evaluate contract."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "LabelGuard AI Legal Engine"}


def test_evaluate_empty_input_returns_all_registry_rules() -> None:
    response = client.post("/api/v1/evaluate", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["rules_evaluated"] > 0
    assert len(body["results"]) == body["rules_evaluated"]
    for result in body["results"]:
        assert result["status"] in {
            "COMPLIANT", "VIOLATION", "REVIEW_REQUIRED", "NOT_VERIFIABLE", "NOT_APPLICABLE",
        }
        assert result["source"]["document"] == "Legal Metrology (Packaged Commodities) Rules, 2011"
        # Unverified pages are never claimed.
        if result["source"]["page"] is not None:
            assert isinstance(result["source"]["page"], int) and result["source"]["page"] > 0


def test_evaluate_requires_wellformed_body() -> None:
    response = client.post("/api/v1/evaluate", json={"product": {"mrp": "not-a-dict"}})
    assert response.status_code == 422
