# LabelGuard AI — Legal Engine

Deterministic, explainable evaluation of package-label information against the

> **Legal Metrology (Packaged Commodities) Rules, 2011**

The engine answers one question per registered rule: *does the supplied
structured evidence establish that this rule's condition is satisfied?* It is
an **automated assessment tool, not legal certification** — it never outputs
"Product is legally certified", never scores compliance, and never converts
missing information into a violation.

## Legal source

- Document: *Legal Metrology (Packaged Commodities) Rules, 2011* (the PDF
  supplied with this project).
- Every `RuleResult.source` cites that document. `source_page` stays `null`
  until a page number has been verified against the supplied PDF — page
  numbers are never guessed.
- Schedule numerics (First Schedule MPE, Rule 7 letter-height tables, Second
  Schedule specified quantities, Third/Fourth Schedule lists) live only in
  `app/rules/schedule_data.py`, and every row is verification-gated
  (`verified` + `source_page`). See **docs/schedule-population.md**.
- The supplied PDF was not present in the build environment, so all schedule
  datasets ship **empty and unverified**; Schedule-dependent checks therefore
  return `NOT_VERIFIABLE` rather than run on remembered values.

## Implemented rule groups (this phase)

| rule_id | rule_number | check |
| --- | --- | --- |
| `LMPC-R6-A`…`F` | Rule 6 | presence of the mandatory declarations: party name, product name, net quantity, month-year, MRP, consumer care |
| `LMPC-R7-A` | Rule 7 | principal display panel detection |
| `LMPC-R7-B` | Rule 7 | minimum numeral height (data-gated on the First Schedule tables) |
| `LMPC-R8-A` | Rule 8 | declarations appear on the principal display panel (region evidence only) |
| `LMPC-R9-A` | Rule 9 | legibility/prominence (contrast evidence or review) |
| `LMPC-R9-B` | Rule 9 | declaration language (detection evidence or review) |
| `LMPC-R10-A/B/C` | Rule 10 | responsible party, importer for imports, address |
| `LMPC-R11-A` | Rule 11 | net quantity declared; "when packed" applicability via Third Schedule data |
| `LMPC-R12-A` | Rule 12 | quantity unit kind (mass/length/area/volume/number); Fourth Schedule exceptions via data |
| `LMPC-R13-A` | Rule 13 | unit symbol representation |

**Not yet implemented:** Rules 3, 4, 5, 14–18, 19-onward (inspection/testing),
24 (wholesale), 25 (export), 26 (exemptions), 27-onward (registration), 31
(advertisements), Fifth–Seventh Schedules (sampling/testing), and the
numeric threshold comparisons that need the verified schedule tables.

## Evaluation states

| state | meaning |
| --- | --- |
| `COMPLIANT` | the supplied evidence establishes the condition is satisfied |
| `VIOLATION` | the supplied evidence establishes the condition is **not** satisfied |
| `REVIEW_REQUIRED` | a possible issue that deterministic evaluation cannot settle |
| `NOT_VERIFIABLE` | required information/evidence is unavailable |
| `NOT_APPLICABLE` | the rule does not apply to this package |

Central policy: **missing information is never a violation.** A VIOLATION for
an absent declaration requires the pipeline to affirm the whole label was
captured and read (`visual_evidence.label_fully_processed = true`). Results
needing human judgment carry `requires_officer_verification: true`, and any
future officer override is stored separately — the automated result is never
overwritten.

## API

`GET /health` → `{"status": "ok", "service": "LabelGuard AI Legal Engine"}`

`POST /api/v1/evaluate`:

```json
{
  "product": {
    "product_name": "Biscuits (Vanilla)",
    "manufacturer": "ABC Foods Pvt Ltd",
    "address": "Plot 12, Industrial Estate, Vijayawada",
    "net_quantity": 250.0,
    "quantity_unit": "g",
    "mrp": {"amount": 50.0, "currency": "INR"},
    "manufacture_month": 8,
    "manufacture_year": 2026,
    "consumer_care": "care@abcfoods.example"
  },
  "package": {"commodity_category": "biscuits"},
  "visual_evidence": {"label_fully_processed": true}
}
```

Response:

```json
{
  "status": "success",
  "rules_evaluated": 17,
  "results": [
    {
      "rule_id": "LMPC-R6-E",
      "rule_number": "6(1)",
      "title": "Retail sale price (MRP)",
      "status": "COMPLIANT",
      "severity": "mandatory",
      "finding": "Required declaration is present in the supplied information.",
      "required_information": ["mrp"],
      "actual_information": {"mrp": {"amount": 50.0, "currency": "INR"}},
      "evidence": [],
      "confidence": null,
      "source": {"document": "Legal Metrology (Packaged Commodities) Rules, 2011", "page": null},
      "requires_officer_verification": false
    }
  ]
}
```

There is deliberately **no overall compliance score** — scoring arrives only
after the rule framework is stable.

## Adding a new rule

1. Define a `RuleDefinition` in a `rule_N.py` module (rule_id, number, title,
   required fields, severity, evaluation type; `source_page` only if verified).
2. Write its evaluator: a function `EvaluationInput -> RuleResult` that returns
   exactly one `EvaluationState`. Use `app/rules/support.py` helpers so the
   missing-evidence policy stays uniform.
3. Append the `(definition, evaluator)` pair to that module's `*_RULES` list —
   the registry picks it up; **no other file changes** (no `if rule == ...`
   branching exists anywhere).
4. Add tests: one per state the rule can produce, including the
   missing-evidence case.

## Running

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8003
pytest tests/ -q
```

## Warning

This engine is an **automated, AI-assisted compliance assessment** component.
It does not provide legal advice, does not certify products, and its findings
— especially `REVIEW_REQUIRED` and `NOT_VERIFIABLE` results — must be verified
by a qualified Legal Metrology officer before any conclusion is drawn.
