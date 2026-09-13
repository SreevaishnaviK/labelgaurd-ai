# LabelGuard AI

AI-powered compliance inspection for packaged commodity labels. **Analyze. Verify. Comply.**

LabelGuard AI inspects packaged-commodity labels, extracts declared information, evaluates Legal
Metrology requirements, and produces evidence-backed assessments for officer verification.

> **Status: Phase 3 — Structured Information Extraction.** Upload a real label and the backend
> stores the original, runs preprocessing + Tesseract OCR in the computer-vision service, then
> sends the OCR output (never the image) to the AI service for deterministic field extraction.
> Structured fields — with detected/not_detected/ambiguous status, separate OCR and extraction
> confidence, and evidence references back to OCR blocks — persist in PostgreSQL and drive the
> frontend's Structured Information panel. Legal Metrology rules and compliance scoring arrive
> in later phases — nothing here fabricates results or judges compliance.

## Phase 2 — OCR pipeline

```text
Upload (frontend) → POST /api/v1/inspections/upload (backend)
  → original stored under uploads/originals/<uuid>.<ext>
  → forwarded to POST /api/v1/analyze (computer-vision)
      load safely → EXIF orientation → perspective correction (only when confident)
      → resize → grayscale → contrast → denoise → adaptive threshold → light sharpen
      → Tesseract OCR (engine-agnostic BaseOCREngine abstraction)
  → pages, blocks, confidence, pixel bboxes persisted (OCRDocument / OCRBlock)
  → GET /api/v1/inspections/{inspection_id} powers the OCR result screen
```

- **Supported inputs:** PNG, JPG, JPEG, PDF (max 20 MB). MIME, extension, size, and decodability
  are all validated; the filename alone is never trusted. PDFs are converted per page with
  `pdf2image` and OCR'd independently — page coordinates are never merged.
- **Safety:** originals are never modified; processed variants are stored separately under
  `uploads/processed/`. Storage names are UUIDs (path-traversal safe), filesystem paths are never
  exposed through APIs, and backend→CV calls have a configurable timeout with `failed` status
  persisted on error.
- **Key APIs** (all documented in each service's Swagger UI):

```http
POST /api/v1/inspections/upload      # multipart file → inspection + OCR summary
GET  /api/v1/inspections/{id}        # inspection + full OCR payload
GET  /api/v1/inspections/{id}/image  # original upload (evidence viewer)
POST /api/v1/analyze                 # computer-vision: multipart file → OCR result
```

Upload response example:

```json
{
  "inspection_id": "LGA-2026-00001",
  "status": "processed",
  "filename": "label.jpg",
  "document_type": "image",
  "pages": 1,
  "text_length": 842,
  "blocks_detected": 74
}
```

OCR blocks carry raw pixel coordinates against the processed page dimensions, numeric 0–100
confidence from Tesseract, and reading-order text; the frontend overlays them responsively over
the original image with a toggle.

- **Tesseract in Docker:** the computer-vision image installs `tesseract-ocr` and
  `poppler-utils` (PDF rasterization) on top of the Python/OpenCV stack — no host install needed.
  For local (non-Docker) runs, install Tesseract + Poppler and have them on `PATH` (pytesseract
  and pdf2image discover them automatically); the integration tests skip when the binaries are
  absent.
- **Phase 2 models:** `Inspection` gains file/processing fields; `OCRDocument` and `OCRBlock`
  store page-level results with proper foreign keys (Alembic migration `0002`).

## Phase 3 — Structured information extraction

```text
OCR persisted (Phase 2)
  → backend assembles OCR pages (text + confidence + bboxes, never the image)
  → POST /api/v1/extract (ai service, http://ai:8002)
      DeterministicFieldExtractor (rule-based, no LLM, no network, no API keys)
      — 23 fields: product name, manufacturer/packer/importer + addresses,
        net quantity, MRP, dates, batch/lot, consumer care contacts, origin,
        ingredients, veg/non-veg declaration
      — statuses: detected | not_detected | ambiguous (ambiguous is never resolved)
  → ExtractedField + ExtractedFieldEvidence persisted (Alembic migration 0004)
  → GET /api/v1/inspections/{id} now returns `extraction.fields` alongside `ocr`
  → frontend Structured Information panel: value, status, confidences, and an
    Evidence button that highlights the referenced OCR block on the label
```

- **Evidence linking:** every field references existing OCR block IDs — coordinates are never
  duplicated. Clicking a field's evidence highlights its block in the existing bbox overlay.
- **No compliance leakage:** the AI service only reports what text *represents*. Words like
  compliant, violation, or score appear nowhere in extraction output; missing fields display
  "Not detected", never "Violation".
- **Extensibility:** `BaseFieldExtractor` is the contract; `DeterministicFieldExtractor` ships
  today and an LLM-backed extractor can be added later behind the same API (config-selected).
- **Key APIs added:**

```http
POST /api/v1/extract                # ai service: OCR pages in → structured fields out
```

---

## Architecture

```text
                 ┌──────────────┐
                 │   FRONTEND   │
                 │ React / Vite │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │   BACKEND    │
                 │   FastAPI    │
                 └──────┬───────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
   ┌────────────┐ ┌───────────┐ ┌──────────────┐
   │ COMPUTER   │ │    AI     │ │    LEGAL     │
   │  VISION    │ │  SERVICE  │ │    ENGINE    │
   └────────────┘ └───────────┘ └──────────────┘
                        │
                        ▼
                 ┌──────────────┐
                 │  PostgreSQL  │
                 └──────────────┘
```

- **Frontend** talks *only* to the backend.
- **Backend** orchestrates the three internal services and owns the database.
- Services communicate over the Docker network using service names (never `localhost`).

## Project structure

```text
LabelGuard-AI/
├── frontend/          React + TypeScript + Vite + Tailwind (port 5173)
├── backend/           FastAPI orchestration + PostgreSQL (port 8000)
├── computer-vision/   Preprocessing + Tesseract OCR service (port 8001)
├── ai/                Field extraction skeleton (port 8002)
├── legal-engine/      Compliance rule engine skeleton (port 8003)
├── docker-compose.yml
└── README.md
```

## Prerequisites

- **Docker + Docker Compose** — recommended; runs the whole system
- **Node 20+** and **Python 3.11+** — only for per-service local development
- **PostgreSQL 16** — or use the bundled Docker service

## Environment variables

Every service ships a `.env.example`. Copy it to `.env` and adjust:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

| Service         | File                      | Key variables                                                        |
| --------------- | ------------------------- | -------------------------------------------------------------------- |
| frontend        | `frontend/.env`           | `VITE_API_URL=http://localhost:8000`                                 |
| backend         | `backend/.env`            | `DATABASE_URL`, `CORS_ORIGINS`, `CV_SERVICE_URL`, `AI_SERVICE_URL`, `LEGAL_ENGINE_URL` |
| computer-vision | `computer-vision/.env`    | `SERVICE_PORT=8001`                                                  |
| ai              | `ai/.env`                 | `SERVICE_PORT=8002`                                                  |
| legal-engine    | `legal-engine/.env`       | `SERVICE_PORT=8003`                                                  |

Never commit real credentials — `.env` files are git-ignored. In Docker Compose the PostgreSQL
password comes from the `POSTGRES_PASSWORD` environment variable (defaults to `password` for
development).

## Docker development (primary)

```bash
docker compose up --build
```

This starts all six services: frontend, backend, computer-vision, ai, legal-engine, and PostgreSQL
with a persistent volume. Stop with `Ctrl+C`, then `docker compose down`.

## Local development (per service)

**Frontend**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # set DATABASE_URL to your PostgreSQL instance
uvicorn app.main:app --reload --port 8000
```

**Computer Vision / AI / Legal Engine** (same pattern, different ports):

```bash
cd computer-vision               # or ai/ or legal-engine/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001   # 8002 for ai/, 8003 for legal-engine/
```

## Service ports

| Service         | URL                        |
| --------------- | -------------------------- |
| Frontend        | http://localhost:5173      |
| Backend         | http://localhost:8000      |
| Computer Vision | http://localhost:8001      |
| AI              | http://localhost:8002      |
| Legal Engine    | http://localhost:8003      |
| PostgreSQL      | localhost:5432             |

## Database setup

PostgreSQL connection is configured via `DATABASE_URL`, e.g.:

```text
postgresql+psycopg://labelguard:password@localhost:5432/labelguard
```

Schema migrations are managed with Alembic — tables are never created at application startup:

```bash
cd backend
alembic upgrade head                                # apply all migrations
alembic revision --autogenerate -m "initial schema" # create a new migration
```

Phase 1 models: `Inspection`, `Product` (nullable fields), and `AuditLog`. Phase 2 extends
`Inspection` with file/processing metadata and adds `OCRDocument` + `OCRBlock`.

## Health checks

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

Aggregated status (database + all three internal services):

```bash
curl http://localhost:8000/api/v1/system/status
```

Unavailable dependencies are reported as `"unavailable"` — the endpoint never crashes.

## API documentation

Interactive docs for each service:

| Service         | Swagger UI                  | ReDoc                  |
| --------------- | --------------------------- | ---------------------- |
| Backend         | http://localhost:8000/docs  | http://localhost:8000/redoc |
| Computer Vision | http://localhost:8001/docs  | http://localhost:8001/redoc |
| AI              | http://localhost:8002/docs  | http://localhost:8002/redoc |
| Legal Engine    | http://localhost:8003/docs  | http://localhost:8003/redoc |

## Development phases

| Phase | Scope                                                        | Status         |
| ----- | ------------------------------------------------------------ | -------------- |
| 1     | System foundation: services, health checks, PostgreSQL       | Done           |
| 2     | Computer vision: upload, preprocessing, OCR, bounding boxes  | **Current**    |
| 3     | Inspection workflow and persistence                          | Planned        |
| 4     | AI extraction and assessment                                 | Planned        |
| 5     | Legal Metrology rule engine and compliance evaluation        | Planned        |
| 6     | Reporting, officer verification workflow                     | Planned        |

## Tests

Each Python service ships pytest coverage of its endpoints:

```bash
cd backend && pytest        # repeat for computer-vision/, ai/, legal-engine/
```
