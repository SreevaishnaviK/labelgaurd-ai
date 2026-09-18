"""Report content regression tests (Phase 9 pass).

Grounded in §32 of the phase spec: the report must not "correct" the
extraction. An explicitly NOT_DETECTED field (e.g. net quantity) appears as
"Not detected from available evidence" — never as a fabricated value — and
structured values like MRP render with their amount, not just the currency.
"""

import re

from tests.conftest import png_bytes


def _pdf_text(pdf_bytes: bytes) -> str:
    """Content streams are written uncompressed (pageCompression=0);
    extract every PDF string operand and join them in order."""
    raw = pdf_bytes.decode("latin-1", errors="ignore")
    operands = re.findall(r"\((.*?)(?<!\\)\)", raw)
    return " ".join(
        op.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\") for op in operands
    )


def _run_pipeline_and_generate(client, seed_fields):
    """Full pipeline with the stub AI returning `seed_fields`, then generate
    the report. Returns (inspection_id, evaluation, pdf_text)."""
    from tests.test_reporting import _evaluate, _full_pipeline  # reuse stubs

    inspection_id, evaluation = _full_pipeline(client)
    if seed_fields:
        from app.database import SessionLocal
        from app.models.inspection import ExtractedField, Inspection

        session = SessionLocal()
        insp = session.query(Inspection).filter(Inspection.inspection_id == inspection_id).one()
        for f in seed_fields:
            session.add(
                ExtractedField(
                    inspection_id=insp.id,
                    field_name=f["field_name"],
                    status=f["status"],
                    value_json=f["value"],
                    method=f.get("method", "deterministic"),
                    extraction_confidence=f.get("extraction_confidence", 90.0),
                )
            )
        session.commit()
        session.close()
        # Re-evaluate so rule results see the extra fields.
        evaluation = _evaluate(client, inspection_id)
    response = client.post(f"/api/v1/inspections/{inspection_id}/report")
    assert response.status_code == 201, response.text
    return inspection_id, evaluation


class TestReportContent:
    def test_not_detected_field_rendered_not_fabricated(self, client):
        """net_quantity NOT_DETECTED → explicit 'Not detected' row, no '52 g'."""
        inspection_id, _ = _run_pipeline_and_generate(
            client,
            [{"field_name": "net_quantity", "status": "not_detected", "value": None}],
        )
        text = _pdf_text(client.get(f"/api/v1/inspections/{inspection_id}/report/download").content)
        assert "Net quantity" in text
        assert "Not detected from available evidence" in text
        # The one fabrication the phase spec calls out by name.
        assert "52 g" not in text
        assert "52g" not in text

    def test_mrp_amount_renders_with_currency(self, client):
        """MRP {amount: 30.0, currency: INR} → 'INR 30.00', never bare 'INR'."""
        inspection_id, _ = _run_pipeline_and_generate(
            client,
            [{"field_name": "mrp", "status": "detected", "value": {"amount": 30.0, "currency": "INR"}}],
        )
        text = _pdf_text(client.get(f"/api/v1/inspections/{inspection_id}/report/download").content)
        assert "INR 30.00" in text

    def test_rule_block_has_officer_line_and_severity(self, client):
        """§16: every rule block carries required/actual info, severity, and an
        explicit officer-verification line."""
        inspection_id, evaluation = _run_pipeline_and_generate(client, [])
        text = _pdf_text(client.get(f"/api/v1/inspections/{inspection_id}/report/download").content)
        assert text.count("Officer verification: Not yet verified") >= 10
        assert "Severity:" in text
        assert "Required information:" in text
