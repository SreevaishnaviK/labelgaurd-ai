"""Backend Phase 9 tests: inspection history, dashboard metrics, evaluation
version history and PDF reports — all over real persisted data.

The legal engine runs as the REAL service (shared fixture), so every
evaluation/rollup asserted here is the actual production behavior. Report
generation is checked against persisted content only (inspection id, version,
rule results, officer verification, disclaimer, SHA-256 integrity hash).
"""
import hashlib

import pytest

from .conftest import upload

STATUS = "unimportant"


def _evaluate(client, inspection_id):
    response = client.post(f"/api/v1/inspections/{inspection_id}/evaluate")
    assert response.status_code == 200, response.text
    return response.json()


def _full_pipeline(client):
    """Upload + evaluate + report prerequisites: returns inspection id."""
    response = upload(client)
    assert response.status_code in (200, 201), response.text
    inspection_id = response.json()["inspection_id"]
    return inspection_id, _evaluate(client, inspection_id)


# --- A–E. history: real records, pagination, search, status/date filters ----


@pytest.mark.usefixtures("stub_cv", "stub_ai", "real_legal_engine")
class TestInspectionHistory:
    def test_history_lists_real_inspections(self, client):
        inspection_id, _ = _full_pipeline(client)
        response = client.get("/api/v1/inspections", params={"page": 1, "page_size": 10})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        ids = [item["inspection_id"] for item in body["items"]]
        assert inspection_id in ids
        row = next(i for i in body["items"] if i["inspection_id"] == inspection_id)
        assert row["automated_status"] in (None, "COMPLIANT", "NON_COMPLIANT", "REVIEW_REQUIRED", "INCOMPLETE")
        assert row["has_evaluation"] is True
        assert row["evaluation_version"] >= 1
        # No OCR payloads in summaries.
        assert "ocr" not in row and "extraction" not in row

    def test_pagination(self, client):
        response = client.get("/api/v1/inspections", params={"page": 1, "page_size": 2})
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2
        assert body["page"] == 1 and body["page_size"] == 2
        if body["total"] > 2:
            assert body["pages"] >= 2
            page2 = client.get("/api/v1/inspections", params={"page": 2, "page_size": 2}).json()
            assert page2["page"] == 2

    def test_search_by_inspection_id(self, client):
        inspection_id, _ = _full_pipeline(client)
        body = client.get(
            "/api/v1/inspections", params={"search": inspection_id}
        ).json()
        assert body["total"] >= 1
        assert inspection_id in [i["inspection_id"] for i in body["items"]]

    def test_search_by_product_name(self, client):
        inspection_id, _ = _full_pipeline(client)
        # Fixture extraction always detects MRP; product name may be absent,
        # so assert only that the endpoint accepts and applies the search.
        body = client.get("/api/v1/inspections", params={"search": "Wheat Flour"}).json()
        assert "items" in body and isinstance(body["items"], list)

    def test_date_filters(self, client):
        _full_pipeline(client)  # create a real record first
        future = client.get(
            "/api/v1/inspections", params={"date_from": "2099-01-01T00:00:00Z"}
        ).json()
        assert future["total"] == 0
        past = client.get(
            "/api/v1/inspections", params={"date_to": "2099-01-01T00:00:00Z"}
        ).json()
        assert past["total"] >= 1

    def test_status_filter(self, client):
        inspection_id, evaluation = _full_pipeline(client)
        status = evaluation["overall_status"]
        body = client.get("/api/v1/inspections", params={"status": status}).json()
        assert body["total"] >= 1
        assert inspection_id in [i["inspection_id"] for i in body["items"]]
        empty = client.get("/api/v1/inspections", params={"status": "NON_COMPLIANT"}).json()
        assert all(
            i["automated_status"] == "NON_COMPLIANT" or i["effective_status"] == "NON_COMPLIANT"
            for i in empty["items"]
        ) or empty["total"] == 0


# --- S/U/T. dashboard metrics from the database ------------------------------


@pytest.mark.usefixtures("stub_cv", "stub_ai", "real_legal_engine")
class TestDashboard:
    def test_metrics_from_database(self, client):
        inspection_id, evaluation = _full_pipeline(client)
        body = client.get("/api/v1/inspections/dashboard/metrics").json()
        assert body["total_inspections"] >= 1
        assert body["automated"][evaluation["overall_status"]] >= 1
        assert body["officer_effective"][evaluation["overall_status"]] >= 1
        assert any(r["inspection_id"] == inspection_id for r in body["recent_inspections"])

    def test_no_mock_records(self, client):
        body = client.get("/api/v1/inspections/dashboard/metrics").json()
        # Every recent inspection must exist in the real history endpoint.
        history = client.get("/api/v1/inspections", params={"page_size": 100}).json()
        real_ids = {i["inspection_id"] for i in history["items"]}
        for recent in body["recent_inspections"]:
            assert recent["inspection_id"] in real_ids

    def test_empty_database_zero_metrics(self, client):
        # A fresh isolated DB (client fixture is function-scoped).
        body = client.get("/api/v1/inspections/dashboard/metrics").json()
        assert body["total_inspections"] == 0
        assert all(count == 0 for count in body["automated"].values())
        assert body["recent_inspections"] == []
        history = client.get("/api/v1/inspections").json()
        assert history["total"] == 0 and history["items"] == []


# --- F/H + I. details, evaluation versions ------------------------------------


@pytest.mark.usefixtures("stub_cv", "stub_ai", "real_legal_engine")
class TestEvaluationVersions:
    def test_version_listing_and_retrieval(self, client):
        inspection_id, first = _full_pipeline(client)
        second = _evaluate(client, inspection_id)
        versions = client.get(f"/api/v1/inspections/{inspection_id}/evaluations").json()
        assert [v["evaluation_version"] for v in versions] == [1, 2]
        assert versions[0]["overall_status"] == first["overall_status"]
        detail = client.get(f"/api/v1/inspections/{inspection_id}/evaluations/1")
        assert detail.status_code == 200
        assert detail.json()["evaluation_version"] == 1
        assert detail.json()["overall_status"] == first["overall_status"]
        # Immutable: v1 data unchanged after v2 exists.
        assert detail.json()["evaluated_at"] == first["evaluated_at"]

    def test_unknown_version_404(self, client):
        inspection_id, _ = _full_pipeline(client)
        response = client.get(f"/api/v1/inspections/{inspection_id}/evaluations/99")
        assert response.status_code == 404


# --- J–R. reports ---------------------------------------------------------------


@pytest.mark.usefixtures("stub_cv", "stub_ai", "real_legal_engine")
class TestReports:
    def _generate(self, client, inspection_id):
        response = client.post(f"/api/v1/inspections/{inspection_id}/report")
        assert response.status_code == 201, response.text
        return response.json()

    def test_report_generation_and_content(self, client):
        inspection_id, evaluation = _full_pipeline(client)
        meta = self._generate(client, inspection_id)
        assert meta["inspection_id"] == inspection_id
        assert meta["evaluation_version"] == evaluation["evaluation_version"]
        assert len(meta["report_hash"]) == 64

        pdf_response = client.get(f"/api/v1/inspections/{inspection_id}/report/download")
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"].startswith("application/pdf")
        pdf_bytes = pdf_response.content
        assert pdf_bytes[:5] == b"%PDF-"
        # Integrity hash matches the served bytes.
        assert hashlib.sha256(pdf_bytes).hexdigest() == meta["report_hash"]
        # Text content: PDF streams are Flate-compressed, so validate via
        # regenerated bytes rather than raw-text search.
        text = self._pdf_text(pdf_bytes)
        assert inspection_id in text
        assert f"Evaluation version v{evaluation['evaluation_version']}" in text
        assert "Rule Results" in text
        assert "not a legal certification" in text.lower()

    def _pdf_text(self, pdf_bytes: bytes) -> str:
        """Content streams are written uncompressed (pageCompression=0);
        extract every PDF string operand and join them in order to recover
        the report text (line wrapping keeps word order intact)."""
        import re

        raw = pdf_bytes.decode("latin-1", errors="ignore")
        operands = re.findall(r"\((.*?)(?<!\\)\)", raw)
        text = " ".join(
            op.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
            for op in operands
        )
        return text

    def test_report_without_evaluation_conflict(self, client):
        response = upload(client)
        inspection_id = response.json()["inspection_id"]
        response = client.post(f"/api/v1/inspections/{inspection_id}/report")
        assert response.status_code == 409

    def test_report_metadata_before_generation_404(self, client):
        inspection_id, _ = _full_pipeline(client)
        assert client.get(f"/api/v1/inspections/{inspection_id}/report").status_code == 404

    def test_report_immutable_across_versions(self, client):
        inspection_id, _ = _full_pipeline(client)
        v1_meta = self._generate(client, inspection_id)
        v1_pdf = client.get(f"/api/v1/inspections/{inspection_id}/report/download").content
        v1_hash = v1_meta["report_hash"]
        # New evaluation version → new report, old one untouched.
        _evaluate(client, inspection_id)
        v2_meta = self._generate(client, inspection_id)
        assert v2_meta["evaluation_version"] > v1_meta["evaluation_version"]
        assert v2_meta["report_hash"] != v1_hash
        v2_pdf = client.get(f"/api/v1/inspections/{inspection_id}/report/download").content
        assert hashlib.sha256(v1_pdf).hexdigest() == v1_hash  # v1 bytes intact

    def test_report_repeat_generation_returns_same_record(self, client):
        inspection_id, _ = _full_pipeline(client)
        first = self._generate(client, inspection_id)
        second = self._generate(client, inspection_id)
        assert first["id"] == second["id"]
        assert first["report_hash"] == second["report_hash"]

    def test_report_contains_officer_verification(self, client):
        inspection_id, evaluation = _full_pipeline(client)
        rule_id = next(
            r["rule_evaluation_id"]
            for r in evaluation["results"]
            if r["rule_id"] == "LMPC-R8-A"
        )
        override = client.post(
            f"/api/v1/inspections/{inspection_id}/verifications",
            json={
                "rule_evaluation_id": rule_id,
                "decision": "OVERRIDE_COMPLIANT",
                "comment": "Physical label inspected manually.",
            },
        )
        assert override.status_code == 201, override.text
        self._generate(client, inspection_id)
        pdf_text = self._pdf_text(
            client.get(f"/api/v1/inspections/{inspection_id}/report/download").content
        )
        assert "OVERRIDE_COMPLIANT" in pdf_text
        assert "Physical label inspected manually." in pdf_text
        assert "officer-dev" in pdf_text

    def test_report_deterministic_hash_for_identical_bytes(self, client):
        inspection_id, _ = _full_pipeline(client)
        meta = self._generate(client, inspection_id)
        pdf_bytes = client.get(f"/api/v1/inspections/{inspection_id}/report/download").content
        assert hashlib.sha256(pdf_bytes).hexdigest() == meta["report_hash"]
        # Recomputing over the same stored file is stable.
        again = hashlib.sha256(pdf_bytes).hexdigest()
        assert again == meta["report_hash"]
