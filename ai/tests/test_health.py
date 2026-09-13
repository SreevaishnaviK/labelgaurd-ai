"""AI service health and extract contract tests."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "LabelGuard AI AI Service"}


def test_extract_requires_pages() -> None:
    response = client.post("/api/v1/extract", json={"inspection_id": "LGA-2026-00001", "pages": []})
    assert response.status_code == 422


def test_extract_returns_full_field_set() -> None:
    response = client.post(
        "/api/v1/extract",
        json={
            "inspection_id": "LGA-2026-00001",
            "pages": [
                {
                    "page_number": 1,
                    "width": 800,
                    "height": 400,
                    "full_text": "nothing useful",
                    "blocks": [{"id": "block_001", "text": "nothing useful", "confidence": 50.0}],
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["inspection_id"] == "LGA-2026-00001"
    names = [field["field_name"] for field in body["fields"]]
    # Full stable field set: the prompt's 23 fields + marketer ("Marketed by"
    # is a listed role indicator; its value must not be dropped or mislabeled).
    assert len(names) == 24 and len(set(names)) == 24
    for field in body["fields"]:
        assert field["status"] in ("detected", "not_detected", "ambiguous")
        assert field["method"] == "deterministic"
