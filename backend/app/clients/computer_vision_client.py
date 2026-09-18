"""Client for the Computer Vision OCR service.

The backend never links OCR code — it calls this client. Failures surface as
typed exceptions the inspection service maps to stored failure states; no
fabricated OCR is ever returned.
"""
from dataclasses import dataclass, field

import httpx

from app.config import get_settings


class CVServiceError(Exception):
    """CV service could not be reached or timed out."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CVRejectionError(Exception):
    """CV service rejected the file (validation/processing failure)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CVAnalysisResult:
    status: str
    document_type: str
    pages: list[dict] = field(default_factory=list)
    processing_time_ms: int = 0


@dataclass
class CVEvidenceResult:
    inspection_id: str
    evidence: list[dict] = field(default_factory=list)


def analyze_document(
    *,
    filename: str,
    content: bytes,
    mime_type: str,
) -> CVAnalysisResult:
    """Send the document to the CV service and return a structured result."""
    settings = get_settings()
    url = f"{settings.cv_service_url}/api/v1/analyze"
    try:
        response = httpx.post(
            url,
            files={"file": (filename, content, mime_type)},
            timeout=settings.cv_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise CVServiceError("Computer Vision service timed out.") from exc
    except httpx.HTTPError as exc:
        raise CVServiceError("Computer Vision service is unavailable.") from exc

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", {})
            code = detail.get("code", "CV_PROCESSING_ERROR") if isinstance(detail, dict) else "CV_PROCESSING_ERROR"
            message = detail.get("message", "Computer Vision rejected the document.") if isinstance(detail, dict) else "Computer Vision rejected the document."
        except Exception:
            code, message = "CV_PROCESSING_ERROR", "Computer Vision rejected the document."
        raise CVRejectionError(code, message)

    body = response.json()
    return CVAnalysisResult(
        status=body.get("status", "success"),
        document_type=body.get("document_type", "image"),
        pages=body.get("pages", []),
        processing_time_ms=int(body.get("metadata", {}).get("processing_time_ms", 0)),
    )


def analyze_evidence(
    *,
    inspection_id: str,
    pages: list[dict],
    fields: list[dict],
    original_path: str | None = None,
) -> CVEvidenceResult:
    """Request visual evidence over already-persisted OCR data.

    Sends processed-image references, OCR blocks, and extracted-field
    evidence — never a re-OCR request. ``original_path`` points at the
    unprocessed upload (relative to the CV service's UPLOAD_DIR, which the
    backend shares via volume) so color-dependent visual evidence such as
    declaration-symbol detection can run; without it symbol evidence is
    honestly INSUFFICIENT_EVIDENCE rather than guessed.
    """
    settings = get_settings()
    url = f"{settings.cv_service_url}/api/v1/evidence/analyze"
    payload = {"inspection_id": inspection_id, "pages": pages, "fields": fields}
    if original_path:
        payload["original_path"] = original_path
    try:
        response = httpx.post(url, json=payload, timeout=settings.cv_timeout_seconds)
    except httpx.TimeoutException as exc:
        raise CVServiceError("Computer Vision service timed out.") from exc
    except httpx.HTTPError as exc:
        raise CVServiceError("Computer Vision service is unavailable.") from exc
    if response.status_code != 200:
        if response.status_code >= 500:
            # 5xx from the CV service is a service failure, not a rejection.
            raise CVServiceError(f"Computer Vision evidence analysis failed ({response.status_code}).")
        try:
            detail = response.json().get("detail", {})
            code = detail.get("code", "CV_EVIDENCE_ERROR") if isinstance(detail, dict) else "CV_EVIDENCE_ERROR"
            message = detail.get("message", "Computer Vision rejected the evidence request.") if isinstance(detail, dict) else "Computer Vision rejected the evidence request."
        except Exception:
            code, message = "CV_EVIDENCE_ERROR", "Computer Vision rejected the evidence request."
        raise CVRejectionError(code, message)
    body = response.json()
    return CVEvidenceResult(inspection_id=body.get("inspection_id", inspection_id), evidence=body.get("evidence", []))
