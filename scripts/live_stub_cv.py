"""Temporary stub CV server for the browser live walk; deleted after use.

Returns the Phase 2.1 contract (processed_image, warped). Filenames containing
"warp" flip the warped flag so both frontend overlay branches can be exercised.
"""
from fastapi import FastAPI, UploadFile

app = FastAPI()


@app.post("/api/v1/analyze")
async def analyze(file: UploadFile):
    name = file.filename or ""
    warped = "warp" in name
    return {
        "status": "success",
        "document_type": "image",
        "pages": [
            {
                "page_number": 1,
                "width": 640,
                "height": 480,
                "full_text": "STUB OCR TEXT FOR LIVE CHECK",
                "processed_image": f"processed/stub/page-01.png",
                "warped": warped,
                "blocks": [
                    {
                        "id": "block_001",
                        "text": "STUB OCR TEXT FOR LIVE CHECK",
                        "confidence": 91.5,
                        "bbox": {"x": 10, "y": 20, "width": 300, "height": 40},
                        "line_number": 1,
                        "block_number": 1,
                        "page_number": 1,
                    }
                ],
            }
        ],
        "metadata": {"processing_time_ms": 12},
    }
