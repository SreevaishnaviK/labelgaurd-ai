# LabelGuard AI — AI Service

Structured information extraction over OCR output (Phases 3–4). This service
answers **"what does the OCR text represent?"** — it never makes legal or
compliance judgments (that is the Legal Engine's job, in a later phase).

```
ai/
├── app/
│   ├── main.py                  # FastAPI app
│   ├── config.py                # env-driven settings
│   ├── api/
│   │   └── health.py            # GET /health + POST /api/v1/extract
│   ├── extraction/
│   │   ├── base.py              # BaseFieldExtractor + FIELD_NAMES (source of truth)
│   │   ├── deterministic.py     # rule-based extractor (Phase 3)
│   │   ├── candidates.py        # deterministic results → AI candidate payload
│   │   ├── merger.py            # deterministic + AI merge policy (Phase 4)
│   │   ├── orchestrator.py      # modes, gating, validation, fallback (Phase 4)
│   │   ├── extractor.py         # extractor registry (config-selected)
│   │   └── normalization.py     # currency / unit / date / contact normalizers
│   ├── providers/
│   │   ├── base.py              # BaseAIProvider contract
│   │   ├── mock_provider.py     # scripted provider for tests/demos
│   │   ├── openai_provider.py   # all OpenAI-specific code (Phase 4)
│   │   └── __init__.py          # provider registry (AI_PROVIDER)
│   ├── prompts/
│   │   ├── extraction_system.py # strict no-hallucination system prompt
│   │   └── extraction_user.py   # OCR + candidates as compact JSON
│   ├── schemas/
│   │   └── extraction.py        # request/response/strict AI-output schemas
│   └── utils/
│       └── text.py              # block ordering helpers
└── tests/
```

## API

- `GET /health` — status plus the provider NAME only (never keys/secrets).
- `POST /api/v1/extract` — structured field extraction. Note: the extract
  route lives in `api/health.py` (the service's single router module), not in
  a separate `api/extract.py`.

Request modes:

| mode            | behavior                                          |
| --------------- | ------------------------------------------------- |
| `auto` (default)| deterministic first → AI only where useful        |
| `deterministic` | rules only; a configured provider is never called |
| `ai_assisted`   | AI reviews every field (when configured)          |

## Providers (Phase 4)

`AI_PROVIDER` selects the AI-assisted layer:

- `none` (default) — deterministic extraction only; **no API key required**.
- `mock` — scripted provider for tests/offline demos.
- `openai` — real provider; every OpenAI detail is isolated in
  `providers/openai_provider.py` and reads `OPENAI_API_KEY` / `OPENAI_MODEL`
  from the environment. Failures, timeouts, malformed JSON, unknown field
  names, and invented (evidence-free) fields all degrade safely to
  deterministic extraction (`deterministic_fallback`), never failing the
  inspection.

Gating: in `auto` mode AI is consulted only when deterministic extraction is
ambiguous or below `AI_MIN_DETERMINISTIC_CONFIDENCE` (default 85) — a clean,
confident read never triggers a provider call. Conflicts between
deterministic and AI readings become explicit ambiguous fields with both
candidates preserved (methods attached), never silently overwritten.

## Field contract

Every field reports `status` ∈ `detected | not_detected | ambiguous`,
`method` ∈ `deterministic | ai_assisted | deterministic_fallback`, separate
`ocr_confidence` / `extraction_confidence` / `ai_confidence`, and evidence
referencing existing OCR block IDs (coordinates are never duplicated).
`FIELD_NAMES` in `app/extraction/base.py` is the single source of truth for
the 24-field set; AI fields outside it are rejected as hallucinations.

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8002
```
