# Populating the schedule data from the supplied PDF

The legal-engine's schedule data (`app/rules/schedule_data.py`) ships **empty
and unverified**: no numeric legal value is asserted unless it has been read
and checked against the supplied PDF,

> Legal Metrology (Packaged Commodities) Rules, 2011

When the PDF is available in the repository (e.g. `docs/lmpc-2011.pdf`), use
this procedure to populate each dataset. Until then every Schedule-dependent
check deterministically returns NOT_VERIFIABLE — it cannot and will not run on
remembered values.

## Verification gate

Every dataclass row carries `source_page` and `verified`. A row may only be
committed when:

1. the value was read directly from the supplied PDF, and
2. `source_page` is the page in that PDF where it appears.

Rows with `verified=False` are ignored by all lookup helpers
(`mpe_for`, `letter_height_table`, `second_schedule_entry`, …), so unverified
data can never drive a COMPLIANT/VIOLATION decision.

## Datasets to populate

| dataset | source in the rules | rows |
| --- | --- | --- |
| `FIRST_SCHEDULE_MPE` | First Schedule — Maximum Permissible Error | quantity band, unit, fractional/absolute MPE |
| `LETTER_HEIGHT_TABLE_NORMAL` | Rule 7, Table I (normal containers) | quantity band → minimum numeral height (mm) |
| `LETTER_HEIGHT_TABLE_FORMED` | Rule 7, Table II (blown/formed/moulded/embossed/perforated) | quantity band → minimum numeral height (mm) |
| `SECOND_SCHEDULE` | Second Schedule — specified quantities per commodity | commodity, category key, allowed quantity+unit list |
| `THIRD_SCHEDULE` | Third Schedule — "when packed" commodities | category key, detail |
| `FOURTH_SCHEDULE` | Fourth Schedule — Rule 12(2) exceptions | category key, detail |

## Procedure per dataset

1. Open the supplied PDF and locate the schedule/table (note the page number).
2. Transcribe each row exactly — do not normalize, round, or "fix" values.
3. Add `MpeRow(..., source_page=<pdf page>, verified=True)` (or the matching
   row type) to the list in `app/rules/schedule_data.py`.
4. Extend or add a focused test in `tests/test_rules.py` pinning one transcribed
   value per table (e.g. `assert mpe_for(<value>, "<unit>").mpe_absolute == <n>`),
   so regressions in transcription are caught.
5. Run the suite: `pytest tests/ -q`.

## Category keys

`package.commodity_category` in evaluation input is matched against
`SecondScheduleEntry.category_key` / `ScheduleFlag.category_key`
(e.g. "biscuits", "mineral_water"). When populating the Second Schedule,
choose stable snake_case keys from the commodity names as printed in the PDF,
and list them in the table below so backend/AI callers use identical keys.

| category_key | commodity (as printed in the PDF) |
| --- | --- |
| _(to be filled during population)_ | |

## What activates automatically

Once rows are `verified=True`:

- Rule 7-B compares supplied `estimated_letter_heights_mm` against the
  applicable table (normal vs formed containers) — the evaluator already
  contains the comparison path's data hook.
- Rule 11/12 consult the Third/Fourth Schedule flags for "when packed" and
  Rule 12(2) exceptions.
- Rule 13 / Second-Schedule quantity checks (next phase) read the specified
  quantities directly from the data.

No evaluator code changes are needed — only verified data rows.
