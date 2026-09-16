"""Declaration region evidence: linking extracted fields to visual regions.

The pipeline already knows WHICH text represents which field (extraction
evidence references OCR block ids). This module joins that knowledge to the
blocks' geometry so the answer to "where is the net quantity declared?" is
visual, not inferred. CV only reports where a declaration was detected —
placement legality stays with the Legal Engine.
"""
from app.evidence.geometry import new_evidence_id

# Field names grouped into the declaration categories the prompt lists.
_DECLARATION_CATEGORY = {
    "product_name": "PRODUCT_NAME",
    "manufacturer": "MANUFACTURER",
    "packer": "PACKER",
    "importer": "IMPORTER",
    "marketer": "MANUFACTURER",
    "manufacturer_address": "MANUFACTURER",
    "packer_address": "PACKER",
    "importer_address": "IMPORTER",
    "net_quantity": "NET_QUANTITY",
    "mrp": "MRP",
    "manufacturing_date": "DATE",
    "packing_date": "DATE",
    "best_before": "DATE",
    "use_by": "DATE",
    "expiry_date": "DATE",
    "consumer_care": "CONSUMER_CARE",
    "customer_care_phone": "CONSUMER_CARE",
    "customer_care_email": "CONSUMER_CARE",
    "website": "CONSUMER_CARE",
    "batch_number": "OTHER_MANDATORY_DECLARATION",
    "lot_number": "OTHER_MANDATORY_DECLARATION",
    "country_of_origin": "OTHER_MANDATORY_DECLARATION",
    "ingredients": "OTHER_MANDATORY_DECLARATION",
    "vegetarian_non_vegetarian": "OTHER_MANDATORY_DECLARATION",
}


def declaration_category(field_name: str) -> str:
    return _DECLARATION_CATEGORY.get(field_name, "OTHER_MANDATORY_DECLARATION")


def declaration_regions(
    fields: list[dict], blocks_by_id: dict[str, dict]
) -> list[dict]:
    """One region per extracted field with resolvable OCR evidence.

    A field whose evidence references nothing (or only unknown block ids)
    produces NO region — association is never guessed.
    """
    regions: list[dict] = []
    seen_categories: set[str] = set()
    for field in fields:
        category = declaration_category(field["field_name"])
        refs = field.get("evidence") or []
        anchors = [blocks_by_id[ref["ocr_block_id"]] for ref in refs if ref.get("ocr_block_id") in blocks_by_id]
        if not anchors:
            continue
        x1 = min(b["bbox"]["x"] for b in anchors)
        y1 = min(b["bbox"]["y"] for b in anchors)
        x2 = max(b["bbox"]["x"] + b["bbox"]["width"] for b in anchors)
        y2 = max(b["bbox"]["y"] + b["bbox"]["height"] for b in anchors)
        seen_categories.add(category)
        regions.append(
            {
                "evidence_id": new_evidence_id(),
                "evidence_type": "DECLARATION_REGION",
                "page_number": anchors[0]["page_number"],
                "bbox": {"x": int(x1), "y": int(y1), "width": int(x2 - x1), "height": int(y2 - y1)},
                "value": category,
                "unit": None,
                "confidence": round(min(b["confidence"] for b in anchors) / 100.0, 3),
                "method": "extraction_evidence_join",
                "verification_status": "AUTOMATED",
                "ocr_block_ids": [b["id"] for b in anchors],
                "field_name": field["field_name"],
            }
        )
    return regions
