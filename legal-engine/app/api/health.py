"""Legal Engine API routes.

POST /api/v1/evaluate — deterministic rule evaluation over structured
package data. This is an automated assessment tool: it never certifies
compliance; findings requiring judgment carry requires_officer_verification.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.schemas.evaluation import EvaluationInput, EvaluateSuccess
from app.services.evaluator import evaluate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "LabelGuard AI Legal Engine"}


@router.post("/api/v1/evaluate")
def evaluate_package(request: EvaluationInput) -> EvaluateSuccess:
    try:
        results = evaluate(request)
    except Exception:  # noqa: BLE001 - evaluation must fail loudly, not lie
        logger.exception("Rule evaluation raised unexpectedly")
        raise HTTPException(
            status_code=500,
            detail={"code": "EVALUATION_FAILURE", "message": "Rule evaluation failed."},
        ) from None
    return EvaluateSuccess(status="success", rules_evaluated=len(results), results=results)
