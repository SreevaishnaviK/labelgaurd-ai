# LabelGuard AI

AI-powered compliance inspection for packaged commodity labels. **Analyze. Verify. Comply.**

LabelGuard AI inspects packaged-commodity labels, extracts declared information, evaluates Legal
Metrology requirements, and produces evidence-backed assessments for officer verification.

> **Status: Phase 6 — Full compliance evaluation pipeline.** Upload a real label and the backend
> stores the original, runs preprocessing + Tesseract OCR in the computer-vision service, extracts
> structured fields in the AI service (deterministic patterns, optionally AI-assisted), then calls
> the legal engine to evaluate the extracted information against the implemented Legal Metrology
> (Packaged Commodities) Rules, 2011 checks. Rule results, evidence references, and provenance
> persist in PostgreSQL as immutable evaluation versions and drive the frontend's Structured
> Information and Compliance Assessment panels.
>
> **This is an automated assessment system, not legal certification.** Results support officer
> verification; they never claim a product is legally certified or fully compliant.

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

## Phase 4 — AI-assisted extraction

Extraction keeps its deterministic base and gains an optional AI resolution layer:
`AI_PROVIDER=none|mock|openai` selects the provider (none = deterministic only, no key needed).
In `auto` mode AI is consulted only for ambiguous or low-confidence fields; every AI response is
schema-validated and evidence-checked (hallucinated or evidence-free fields are rejected), and
any provider failure degrades to `deterministic_fallback` without failing the inspection.
Conflicts become `ambiguous` with all candidates persisted (`ExtractionCandidate` rows carry
method + confidence + evidence per reading). Fields expose provenance: `method`, `ai_confidence`,
`resolution_status`.

## Phase 5 — Legal engine foundation + verified schedule data

`legal-engine/` implements deterministic evaluation of Legal Metrology (Packaged Commodities)
Rules, 2011 checks over a structured input model (product / package / visual_evidence — all
nullable). A central rule registry drives 18 checks across Rules 6–13; every result carries one
of five states (see Phase 6 below) and never converts missing evidence into a violation.
Numeric legal values (Rule 7 letter-height tables, First Schedule MPE, Second/Third/Fourth
Schedule entries) were transcribed from the supplied PDF (committed at
`legal-engine/docs/lmpc-2011.pdf`) and are verification-gated: rows without dual-source
agreement stay `verified=False` and cannot drive any conclusion — see
`legal-engine/docs/schedule-population.md`.

## Phase 6 — End-to-end compliance evaluation

```text
Inspection persisted (OCR + extraction)
  → POST /api/v1/inspections/{id}/evaluate (backend)
      build evaluation input from persisted data — only detected fields with
      real evidence are mapped; no visual evidence or package facts are invented
  → POST /api/v1/evaluate (legal engine, http://legal-engine:8003)
      rule registry → per-rule status + finding + source + evidence
  → persist InspectionEvaluation (new immutable version) + RuleEvaluation rows
    + RuleEvaluationEvidence references (block ids / field ids — no duplication)
  → GET /api/v1/inspections/{id} and /evaluation return the latest version
  → frontend Compliance Assessment panel: overall status, rule checklist,
    per-rule evidence buttons that highlight the referenced OCR blocks
```

- **Evaluation states (per rule):** `COMPLIANT` (evidence establishes the requirement is
  satisfied) · `VIOLATION` (evidence establishes it is not) · `REVIEW_REQUIRED` (deterministic
  evaluation cannot settle it — e.g. legibility, or an unmeasured quantity) · `NOT_VERIFIABLE`
  (required evidence unavailable) · `NOT_APPLICABLE` (rule does not apply to this package).
  Missing information is **never** automatically a violation.
- **Overall status:** backend-derived rollup (`COMPLIANT` / `NON_COMPLIANT` / `REVIEW_REQUIRED`
  / `INCOMPLETE`) — a state, not a score. No compliance percentage or score exists anywhere.
- **Evidence traceability:** each rule result links to the extracted fields and OCR block ids
  that support it; the frontend highlights those blocks in the existing overlay. Schedule-backed
  results carry the source document and page.
- **Immutability + versioning:** re-evaluation appends a new `InspectionEvaluation` version
  (`evaluation_version` + 1) — previous automated results are never updated or deleted. Officer
  corrections (a later phase) must be stored separately, never spliced into these records.
- **Key APIs added:**

```http
POST /api/v1/inspections/{id}/evaluate    # run a new evaluation version
GET  /api/v1/inspections/{id}/evaluation  # latest persisted evaluation
POST /api/v1/evaluate                     # (legal engine) direct structured evaluation
```

- **Implemented rules:** Rule 6 declarations (party, product name, net quantity, month-year,
  MRP, consumer care), Rule 7 (PDP detection; letter-height minimums from the verified Rule 7
  tables), Rule 8 (placement — region-evidence gated), Rule 9 (contrast / language —
  review-gated), Rule 10 (party + address, importer for imports), Rule 11 (quantity declared;
  MPE check against verified First Schedule data when a physical measurement is supplied),
  Rule 12 (quantity-unit framework), Rule 13 (unit symbols).
- **Not yet implemented:** Rules 3–5, 14–18, 24–26, 31, First Schedule Table II MPE values
  (unverified transcription), physical quantity testing, officer verification workflow, and any
  form of compliance scoring or legal certification. The engine evaluates only what is
  implemented; everything else remains out of scope until its data is verified from the source.

---

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
`Inspection` with file/processing metadata and adds `OCRDocument` + `OCRBlock`. Phase 3+4 add
`ExtractedField`, `ExtractedFieldEvidence`, and `ExtractionCandidate`. Phase 6 adds the immutable
evaluation trio: `InspectionEvaluation`, `RuleEvaluation`, `RuleEvaluationEvidence`.

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
| 2     | Computer vision: upload, preprocessing, OCR, bounding boxes  | Done           |
| 3     | Structured information extraction + evidence linking         | Done           |
| 4     | AI-assisted extraction (provider abstraction, fallback)      | Done           |
| 5     | Legal engine foundation + verified schedule data             | Done           |
| 6     | End-to-end compliance evaluation + persistence + UI          | **Current**    |
| 7     | Officer verification workflow, reporting                     | Planned        |

## Tests

Each Python service ships pytest coverage of its endpoints:

```bash
cd backend && pytest        # repeat for computer-vision/, ai/, legal-engine/
```
