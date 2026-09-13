"""Computer Vision service schemas."""
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class OCRBlock(BaseModel):
    id: str
    text: str
    confidence: float = Field(ge=0, le=100)
    bbox: BoundingBox
    line_number: int
    block_number: int
    page_number: int


class OCRPage(BaseModel):
    page_number: int
    width: int
    height: int
    full_text: str
    blocks: list[OCRBlock]
    # Geometry of the processed page vs the original upload.
    processed_image: str
    warped: bool


class AnalyzeMetadata(BaseModel):
    processing_time_ms: int


class AnalyzeSuccess(BaseModel):
    status: str
    document_type: str
    pages: list[OCRPage]
    metadata: AnalyzeMetadata


class AnalyzeErrorDetail(BaseModel):
    code: str
    message: str


class AnalyzeError(BaseModel):
    status: str
    error: AnalyzeErrorDetail
