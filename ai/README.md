# LabelGuard AI — AI Service (Phase 3)

Structured information extraction over OCR output. Receives OCR pages
(never images), returns one structured field per known field with statuses,
confidences, and evidence references back to OCR block IDs.

Deterministic and offline: **no LLM, no API keys, no internet access
required.** An LLM-backed extractor can be added later behind the same API
contract. This service never makes legal or compliance judgments — no
compliance scoring, no Legal Metrology rules (those belong to the legal
engine, in a later phase).

## Structure

```text
ai/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app; CORS; includes the API routers
│   ├── config.py                # env settings (extractor selection, confidence floor)
│   ├── api/
│   │   ├── __init__.py
│   │   └── health.py            # GET /health and POST /api/v1/extract
│   │                            # (the extract route lives here, not in a
│   │                            #  separate extract.py — one small router file)
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseFieldExtractor contract
│   │   ├── deterministic.py     # DeterministicFieldExtractor (all fields)
│   │   ├── extractor.py         # get_field_extractor(): config → implementation
│   │   └── normalization.py     # currency / units / phone / email / URL normalizers
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── extraction.py        # request/response pydantic models
│   └── utils/
│       ├── __init__.py
│       └── text.py              # reading-order sorting helpers
├── tests/
├── requirements.txt
└── Dockerfile
```

## API

```http
GET  /health            # liveness: {"status": "ok", "service": ...}
POST /api/v1/extract    # OCR pages in → structured fields out
```

`POST /api/v1/extract` request/response shapes are documented in
`app/schemas/extraction.py` and served at `/docs` (Swagger UI).

## Fields

24 fields, always the full set (undetected fields are reported, never
omitted): product_name, manufacturer, packer, importer, marketer,
manufacturer/packer/importer addresses, net_quantity, mrp,
manufacturing_date, packing_date, best_before, use_by, expiry_date,
consumer_care, customer_care_phone, customer_care_email, website,
batch_number, lot_number, country_of_origin, ingredients,
vegetarian_non_vegetarian.

Every field carries:

- `status`: `detected` | `not_detected` | `ambiguous` — ambiguous candidates
  are surfaced, never silently resolved
- `value`: normalized structured value (raw text is preserved alongside)
- `ocr_confidence`: mean OCR confidence of the evidence blocks ("was the
  text read correctly?")
- `extraction_confidence`: confidence that the matched text represents this
  field ("does this text mean this field?") — deliberately kept separate
  from OCR confidence
- `evidence`: `[{"ocr_block_id", "page_number"}]` references to existing OCR
  blocks — coordinates are never duplicated here

## Running

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8002
pytest tests/
```

In Docker the backend reaches this service at `http://ai:8002` (see
`docker-compose.yml`); the service is independently runnable.
