"""Inspection API schemas."""
from datetime import datetime

from pydantic import BaseModel


class BBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class OCRBlockOut(BaseModel):
    block_id: str
    page_number: int
    text: str
    confidence: float
    bbox: BBox
    line_number: int
    block_number: int


class OCRPageOut(BaseModel):
    page_number: int
    width: int
    height: int
    full_text: str


class UploadSuccess(BaseModel):
    inspection_id: str
    status: str
    filename: str
    document_type: str
    pages: int
    text_length: int
    blocks_detected: int


class UploadFailure(BaseModel):
    status: str
    inspection_id: str
    error: dict


class FileMeta(BaseModel):
    original_filename: str
    document_type: str


class OCRRetrieval(BaseModel):
    pages: list[OCRPageOut]
    blocks: list[OCRBlockOut]
    full_text: str
    blocks_detected: int
    average_confidence: float


class InspectionOut(BaseModel):
    inspection_id: str
    status: str
    created_at: datetime
    file: FileMeta
    ocr: OCRRetrieval


class UploadErrorResponse(BaseModel):
    detail: dict
