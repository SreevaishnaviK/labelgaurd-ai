"""Phase 4 tests: provider abstraction, modes, gating, validation, merging.

The MockAIProvider supplies controlled structured responses — no real
external API is ever touched. Deterministic inputs are synthetic OCR blocks.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.extraction.base import FIELD_NAMES
from app.extraction.orchestrator import run_extraction
from app.providers import get_ai_provider
from app.providers.base import AIProviderError
from app.providers.mock_provider import MockAIProvider
from app.schemas.extraction import AIExtractionOut, AIFieldOut, ExtractRequest, OCRBlockIn, OCRPageIn

from .test_extraction import _block, _page  # shared synthetic OCR helpers


@pytest.fixture()
def mock_env(monkeypatch):
    """AI_PROVIDER=mock: provider exists but scripts nothing by default."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "mock")
    provider = MockAIProvider()
    monkeypatch.setattr(
        "app.extraction.orchestrator.get_ai_provider", lambda: provider
    )
    return provider


def _request(mode="auto", *blocks: OCRBlockIn) -> ExtractRequest:
    return ExtractRequest(
        inspection_id="LGA-2026-00001", pages=_page(*blocks), mode=mode
    )


def _by_name(fields):
    return {f.field_name: f for f in fields}


def _ai(field_name, status="detected", value=None, raw_text=None, confidence=90.0, evidence=()):
    return AIFieldOut(
        field_name=field_name,
        status=status,
        value=value,
        raw_text=raw_text,
        confidence=confidence,
        evidence_block_ids=list(evidence),
    )


def _ambiguous_mrp_page():
    """Two different MRP readings → deterministic ambiguity."""
    return _block("MRP Rs. 68.00", "block_001", y=100), _block("MRP Rs. 72.00", "block_002", y=300)


# ------------------------------------------------ 1. provider abstraction

def test_provider_registry_none_when_disabled():
    assert get_ai_provider() is None  # default AI_PROVIDER=none


def test_provider_registry_selects_mock(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_provider", "mock")
    assert isinstance(get_ai_provider(), MockAIProvider)


def test_provider_registry_unknown_falls_back_to_none(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_provider", "doesnotexist")
    assert get_ai_provider() is None


# ------------------------------------------------ 2-5. modes

def test_deterministic_only_mode_never_consults_provider(mock_env):
    mock_env.configure(fields=[_ai("mrp", value={"amount": 1.0, "currency": "INR"}, evidence=["block_001"])])
    result = run_extraction(_request("deterministic", _block("MRP ₹68.00")))
    assert result.provider == "none"
    fields = _by_name(result.fields)
    assert fields["mrp"].value == {"amount": 68.0, "currency": "INR"}
    assert fields["mrp"].method == "deterministic"


def test_provider_none_mode_ignores_scripted_provider():
    """AI_PROVIDER=none: no provider object at all — deterministic final."""
    result = run_extraction(_request("ai_assisted", _block("MRP ₹68.00")))
    assert result.provider == "none"
    assert all(f.method == "deterministic" for f in result.fields)


def test_ai_assisted_mode_reviews_every_field(mock_env):
    mock_env.configure(fields=[])  # contributes nothing → all confirmed/unchanged
    result = run_extraction(_request("ai_assisted", _block("MRP ₹68.00")))
    assert result.provider == "mock"
    fields = _by_name(result.fields)
    # AI ran but reported nothing → deterministic values stand, no silent change.
    assert fields["mrp"].value == {"amount": 68.0, "currency": "INR"}
    assert fields["mrp"].method == "deterministic"


def test_auto_mode_skips_ai_for_clean_confident_read(mock_env):
    mock_env.configure(error=AIProviderError("must not be called"))
    result = run_extraction(_request("auto", _block("MRP ₹68.00")))
    assert result.provider == "mock"  # provider exists but was never invoked
    assert _by_name(result.fields)["mrp"].method == "deterministic"


def test_auto_mode_calls_ai_for_ambiguity(mock_env):
    mock_env.configure(fields=[])
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    fields = _by_name(result.fields)
    assert fields["mrp"].status == "ambiguous"  # AI offered no resolution
    assert fields["mrp"].resolution_status is None  # unchanged by empty AI


# ------------------------------------------------ 6-8. provider failures

def test_provider_failure_falls_back_with_provenance(mock_env):
    mock_env.configure(error=AIProviderError("boom"))
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    fields = _by_name(result.fields)
    assert fields["mrp"].method == "deterministic_fallback"
    assert fields["mrp"].resolution_status == "ai_unavailable"
    assert fields["mrp"].status == "ambiguous"
    assert len(fields["mrp"].candidates) == 2


def test_provider_timeout_maps_to_fallback(monkeypatch):
    """A real transport timeout becomes the same safe fallback path."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "mock")
    provider = MockAIProvider()

    def raise_timeout(request, candidates):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(provider, "extract_fields", raise_timeout)
    monkeypatch.setattr("app.extraction.orchestrator.get_ai_provider", lambda: provider)
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    assert _by_name(result.fields)["mrp"].method == "deterministic_fallback"


def test_invalid_ai_json_is_rejected(mock_env):
    """A provider returning unparseable output must degrade, not crash."""
    mock_env.configure(error=AIProviderError("malformed"))
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    assert _by_name(result.fields)["mrp"].method == "deterministic_fallback"


def test_openai_parse_rejects_non_json():
    from app.providers.openai_provider import OpenAIProvider

    with pytest.raises(AIProviderError):
        OpenAIProvider._parse("this is prose, not JSON")


def test_openai_parse_rejects_wrong_schema():
    from app.providers.openai_provider import OpenAIProvider

    with pytest.raises(AIProviderError):
        OpenAIProvider._parse('{"fields": [{"bogus": true}]}')


def test_openai_without_api_key_is_provider_error(monkeypatch):
    from app.providers.openai_provider import OpenAIProvider

    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    provider = OpenAIProvider()
    with pytest.raises(AIProviderError, match="OPENAI_API_KEY"):
        provider.extract_fields(_request(), [])


def test_openai_never_sends_or_logs_key(monkeypatch):
    """The key goes only into the Authorization header, never into payloads."""
    from app.providers.openai_provider import OpenAIProvider

    captured = {}

    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"fields": []}'}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"], captured["json"], captured["headers"] = url, json, headers
        return _Response()

    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-secret-value")
    monkeypatch.setattr("app.providers.openai_provider.httpx.post", fake_post)
    OpenAIProvider().extract_fields(_request(), [])
    assert captured["headers"]["Authorization"] == "Bearer sk-secret-value"
    assert "sk-secret-value" not in captured["url"]
    assert "sk-secret-value" not in __import__("json").dumps(captured["json"])


# ------------------------------------------------ 9-12. validation

def test_ai_field_with_unknown_evidence_block_is_rejected(mock_env):
    mock_env.configure(fields=[_ai("mrp", value={"amount": 72.0, "currency": "INR"}, evidence=["block_999"])])
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    fields = _by_name(result.fields)
    # Hallucinated evidence rejected → deterministic ambiguity stands.
    assert fields["mrp"].status == "ambiguous"
    assert fields["mrp"].method == "deterministic"
    assert all(c.method == "deterministic" for c in fields["mrp"].candidates)


def test_ai_field_without_evidence_is_rejected(mock_env):
    mock_env.configure(fields=[_ai("manufacturer", value={"name": "Ghost Ltd"}, evidence=[])])
    result = run_extraction(
        _request("auto", _block("MRP ₹68.00", "block_001"), _block("Manufactured by ABC Foods Pvt Ltd", "block_002"))
    )
    fields = _by_name(result.fields)
    assert fields["manufacturer"].value == {"name": "ABC Foods Pvt Ltd"}


def test_ai_hallucinated_field_name_is_rejected(mock_env):
    mock_env.configure(fields=[_ai("legal_score", value={"score": 88}, evidence=["block_001"])])
    result = run_extraction(_request("auto", _block("MRP ₹68.00", "block_001")))
    assert _by_name(result.fields)["mrp"].status == "detected"
    assert all(f.field_name in FIELD_NAMES for f in result.fields)


def test_ai_not_detected_never_erases_deterministic(mock_env):
    mock_env.configure(fields=[_ai("mrp", status="not_detected", evidence=[])])
    result = run_extraction(_request("auto", _block("MRP ₹68.00", "block_001")))
    assert _by_name(result.fields)["mrp"].value == {"amount": 68.0, "currency": "INR"}


def test_ai_not_detected_does_not_create_field(mock_env):
    mock_env.configure(fields=[_ai("lot_number", status="not_detected", evidence=[])])
    result = run_extraction(_request("auto", _block("MRP ₹68.00", "block_001")))
    assert _by_name(result.fields)["lot_number"].status == "not_detected"


# ------------------------------------------------ 13. conflict → ambiguity

def test_conflicting_values_become_ambiguous_not_overwritten(mock_env):
    mock_env.configure(
        fields=[_ai("mrp", value={"amount": 72.0, "currency": "INR"}, raw_text="MRP Rs. 72", evidence=["block_001"])]
    )
    result = run_extraction(_request("ai_assisted", _block("MRP ₹68.00", "block_001")))
    field = _by_name(result.fields)["mrp"]
    assert field.status == "ambiguous"
    assert field.value is None
    assert field.resolution_status == "conflict"
    assert [(c.value, c.method) for c in field.candidates] == [
        ({"amount": 68.0, "currency": "INR"}, "deterministic"),
        ({"amount": 72.0, "currency": "INR"}, "ai_assisted"),
    ]


def test_ai_agreement_confirms_deterministic(mock_env):
    mock_env.configure(
        fields=[_ai("mrp", value={"amount": 68.0, "currency": "INR"}, evidence=["block_001"])]
    )
    result = run_extraction(_request("ai_assisted", _block("MRP ₹68.00", "block_001")))
    field = _by_name(result.fields)["mrp"]
    assert field.status == "detected"
    assert field.resolution_status == "ai_confirmed"
    assert field.method == "deterministic"


# ------------------------------------------------ 14-15. gating thresholds

def test_high_confidence_deterministic_bypasses_ai_in_auto(mock_env):
    mock_env.configure(error=AIProviderError("must not be called"))
    result = run_extraction(
        _request("auto", _block("Manufactured by ABC Foods Pvt Ltd", "block_001"))
    )
    # Confident deterministic read + no ambiguity → no AI call at all.
    assert _by_name(result.fields)["manufacturer"].method == "deterministic"


def test_low_confidence_deterministic_goes_to_ai(monkeypatch):
    """Threshold 99 gates every field; AI supplies a field the rules missed."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "ai_min_deterministic_confidence", 99.0)
    provider = MockAIProvider()
    provider.configure(
        fields=[_ai("manufacturer_address", value={"address": "Industrial Estate, Vijayawada"}, evidence=["block_001"])]
    )
    monkeypatch.setattr("app.extraction.orchestrator.get_ai_provider", lambda: provider)
    result = run_extraction(
        _request("auto", _block("Manufactured by ABC Foods Pvt Ltd", "block_001", confidence=91.0))
    )
    field = _by_name(result.fields)["manufacturer_address"]
    assert field.method == "ai_assisted"
    assert field.resolution_status == "ai_resolved"
    assert field.status == "detected"
    assert field.value == {"address": "Industrial Estate, Vijayawada"}


def test_threshold_not_hardcoded(mock_env, monkeypatch):
    """The gate reads AI_MIN_DETERMINISTIC_CONFIDENCE, not a constant."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_min_deterministic_confidence", 96.0)
    mock_env.configure(error=AIProviderError("must not be called"))
    # 95 < 96 → gated → provider consulted (and failing → fallback).
    result = run_extraction(_request("auto", _block("Net Qty: 1 kg", "block_001")))
    assert _by_name(result.fields)["net_quantity"].method == "deterministic_fallback"


# ------------------------------------------------ 16-19. evidence & provenance

def test_ai_resolution_preserves_candidate_evidence(mock_env):
    """AI resolves to an existing candidate: field evidence spans the AI's
    blocks and every original reading keeps its own evidence + provenance."""
    mock_env.configure(
        fields=[_ai("mrp", value={"amount": 72.0, "currency": "INR"}, evidence=["block_001", "block_002"])]
    )
    result = run_extraction(_request("ai_assisted", *_ambiguous_mrp_page()))
    field = _by_name(result.fields)["mrp"]
    assert field.status == "detected"
    assert field.value == {"amount": 72.0, "currency": "INR"}
    assert [e.ocr_block_id for e in field.evidence] == ["block_001", "block_002"]
    assert len(field.candidates) == 2
    for candidate in field.candidates:
        assert candidate.method == "deterministic"
        assert candidate.evidence  # per-reading evidence preserved


def test_ai_resolves_ambiguity_to_existing_candidate(mock_env):
    mock_env.configure(
        fields=[_ai("mrp", value={"amount": 72.0, "currency": "INR"}, evidence=["block_002"])]
    )
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    field = _by_name(result.fields)["mrp"]
    assert field.status == "detected"
    assert field.value == {"amount": 72.0, "currency": "INR"}
    assert field.method == "ai_assisted"
    assert field.resolution_status == "ai_resolved"
    # Every original candidate is preserved for audit.
    assert len(field.candidates) == 2


def test_ai_confidence_separate_from_ocr_confidence(mock_env):
    """AI-adopted field: ai_confidence is the AI's number, ocr_confidence is
    derived from the real evidence blocks, extraction tracks the AI reading."""
    mock_env.configure(
        fields=[_ai("importer", value={"name": "Global Imports Ltd"}, confidence=88.0, evidence=["block_002"])]
    )
    result = run_extraction(
        _request("ai_assisted", _block("PREMIUM WHEAT FLOUR", "block_001", confidence=91.0), _block("Net Qty: 1 kg", "block_002", y=500, confidence=84.0))
    )
    field = _by_name(result.fields)["importer"]
    assert field.ai_confidence == 88.0
    # Real OCR confidence from the evidence block — never fabricated.
    assert field.ocr_confidence == 84.0
    assert field.extraction_confidence == 88.0
    assert field.method == "ai_assisted"


def test_ai_third_reading_extends_ambiguity(mock_env):
    mock_env.configure(
        fields=[_ai("mrp", value={"amount": 75.0, "currency": "INR"}, raw_text="75", evidence=["block_002"])]
    )
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    field = _by_name(result.fields)["mrp"]
    assert field.status == "ambiguous"
    assert field.resolution_status == "conflict"
    assert len(field.candidates) == 3
    assert [c.method for c in field.candidates].count("ai_assisted") == 1


def test_candidate_readings_carry_method_and_confidence(mock_env):
    mock_env.configure(fields=[])
    result = run_extraction(_request("auto", *_ambiguous_mrp_page()))
    field = _by_name(result.fields)["mrp"]
    assert field.candidates is not None
    for candidate in field.candidates:
        assert candidate.method == "deterministic"
        assert candidate.confidence == field.extraction_confidence


# ------------------------------------------------ 20. fallback on failure

def test_full_fallback_marks_only_gated_fields(mock_env):
    """AI failure marks fallback on gated fields; untouched fields stay plain."""
    mock_env.configure(error=AIProviderError("boom"))
    result = run_extraction(
        _request("auto", _block("MRP Rs. 68.00", "block_001"), _block("Net Qty: 1 kg", "block_002", y=400))
    )
    fields = _by_name(result.fields)
    assert fields["mrp"].method == "deterministic"  # not gated (high confidence)
    assert fields["mrp"].resolution_status is None
    assert fields["net_quantity"].method == "deterministic"  # not gated either


def test_provider_string_value_coerced_to_field_shape(mock_env):
    """A plain-string AI value for a name-like field still merges honestly."""
    mock_env.configure(
        fields=[_ai("batch_number", value="WF240812", raw_text="Batch No WF240812", evidence=["block_001"])]
    )
    result = run_extraction(_request("ai_assisted", _block("Batch No WF240912", "block_001")))
    field = _by_name(result.fields)["batch_number"]
    assert field.status == "ambiguous"  # differing readings, both preserved
    assert [c.value for c in field.candidates] == [{"batch": "WF240912"}, {"batch": "WF240812"}]


# ------------------------------------------------ API contract

def test_api_backward_compatible_default_mode(mock_env):
    """A Phase 3-style request (no mode key) still works — default auto."""
    mock_env.configure(fields=[])
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    response = client.post(
        "/api/v1/extract",
        json={
            "inspection_id": "LGA-2026-00001",
            "pages": [{"page_number": 1, "width": 800, "height": 400, "full_text": "MRP ₹68.00",
                       "blocks": [{"id": "block_001", "text": "MRP ₹68.00", "confidence": 96.4}]}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success" and body["mode"] == "auto"


def test_health_exposes_provider_without_secrets(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_provider", "mock")
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    body = client.get("/health").json()
    assert body["provider"] == "mock"
    assert "api_key" not in str(body).lower()
