"""LabelGuard AI Computer Vision service — OCR (Phase 2) + evidence (Phase 7)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import analyze, evidence, health

app = FastAPI(
    title="LabelGuard AI Computer Vision",
    version="0.3.0",
    description="Label OCR and visual evidence: validation, preprocessing, text + bounding boxes + confidence, structured measurements.",
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error": {"code": "INVALID_REQUEST", "message": "Missing or malformed request payload."},
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": {"code": "INTERNAL_ERROR", "message": "Unexpected processing failure."},
        },
    )


app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(evidence.router)
