# LabelGuard AI

AI-powered compliance inspection for packaged commodity labels. **Analyze. Verify. Comply.**

LabelGuard AI inspects packaged-commodity labels, extracts declared information, evaluates Legal
Metrology requirements, and produces evidence-backed assessments for officer verification.

> **Status: Phase 1 — System Foundation.** All five services start and expose health endpoints.
> OCR, AI extraction, and compliance rules arrive in later phases. Placeholder endpoints return
> `not_implemented` rather than fake results.

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
├── computer-vision/   Label OCR / region detection skeleton (port 8001)
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

Phase 1 models: `Inspection` (with `uploaded → processing → completed / needs_review / failed`
statuses), `Product` (nullable fields), and `AuditLog`.

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
| 1     | System foundation: services, health checks, PostgreSQL       | **Current**    |
| 2     | Computer vision: label OCR and region detection              | Planned        |
| 3     | Inspection workflow and persistence                          | Planned        |
| 4     | AI extraction and assessment                                 | Planned        |
| 5     | Legal Metrology rule engine and compliance evaluation        | Planned        |
| 6     | Reporting, officer verification workflow                     | Planned        |

## Tests

Each Python service ships pytest coverage of its endpoints:

```bash
cd backend && pytest        # repeat for computer-vision/, ai/, legal-engine/
```
