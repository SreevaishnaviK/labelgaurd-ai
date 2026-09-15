# Schedule data provenance and maintenance

All numeric legal values live in `app/rules/schedule_data.py`, verification-
gated by `verified` + `source_page` on every row. This document records how
the current values were verified and how to amend or extend them.

> Source: *Legal Metrology (Packaged Commodities) Rules, 2011* — committed at
> `legal-engine/docs/lmpc-2011.pdf` (83-page scan, no text layer).

## Verification gate

Every dataclass row carries `source_page` and `verified`. A row may only be
committed when:

1. the value was read directly from the supplied PDF, and
2. `source_page` is the page in that PDF where it appears.

Rows with `verified=False` are ignored by all lookup helpers
(`mpe_for`, `letter_height_table`, `second_schedule_entry`, `third_schedule_flag`,
`fourth_schedule_flag`), so unverified data can never drive a
COMPLIANT/VIOLATION decision.

## How the current values were verified

The PDF is a scan without a text layer. Values were transcribed from page
renders (Poppler at 200–900 dpi) using two independent OCR engines (Tesseract
in the computer-vision container and Windows.Media.Ocr with word coordinates),
plus ink-ROI and cell-grid analysis. Cells whose reads conflicted across
engines were settled by explicit human transcription:

- **First Schedule Table I (p. 72)** — complete. All nine bands verified; the
  percentage column was human-transcribed after OCR disagreement and
  cross-checks against the independent full-page read (row (iv) is an
  absolute 9 g with "—" in the percentage column; row (viii) is 150 g).
- **Rule 7 Table I (p. 47)** — complete: bands (≤200, 200–500, >500 g/ml) ×
  columns (normal: 1/2/4 mm; formed: 2/4/6 mm), read cleanly by both engines.
- **Rule 7 Table II (p. 48)** — complete: PDP-area bands (≤100, 100–500,
  500–2500, >2500 cm²) × columns (normal: 1/2/4/6 mm; formed: 2/4/6/6 mm).
- **Second Schedule (pp. 73–75)** — all 23 commodity rows verified; rows 1–5
  quantity lists were human-settled after row-band overlap confused OCR.
- **Third Schedule (p. 75)** — 3 commodities verified.
- **Fourth Schedule (pp. 75–76)** — all 26 exception entries verified by
  positional row alignment.
- **First Schedule Table II (p. 73)** — *unverified*: its numeric column
  resisted every OCR technique. Only the row structure (length/area/number
  bands) is recorded as a comment in `schedule_data.py`; the values are
  deliberately **not** populated. Transcribe them by hand to activate any
  future rule that needs them.

## Category keys

`package.commodity_category` in evaluation input is matched against
`SecondScheduleEntry.category_key` / `ScheduleFlag.category_key`. The keys in
use (snake_case, derived from the commodity names as printed in the PDF):

| category_key | commodity (as printed) |
| --- | --- |
| `baby_food` | Baby food |
| `weaning_food` | Weaning food |
| `biscuits` | Biscuits |
| `bread` | Bread including brown bread but excluding bun |
| `butter_margarine` | Un-canned packages of butter and margarine |
| `cereals_pulses` | Cereals and Pulses |
| `coffee` | Coffee |
| `tea` | Tea |
| `beverage_mixes` | Materials which may be constituted or reconstituted as beverages |
| `edible_oils` | Edible Oils, Vanaspati, ghee, butter oil |
| `milk_powder` | Milk powder |
| `detergent_powder` | Non-soapy detergents (powder) |
| `atta_rawa_suji` | Atta, rawa and suji |
| `salt` | Salt |
| `soap_laundry` | Laundry soap |
| `soap_non_soapy_cakes` | Non-soapy detergent cakes/bars |
| `soap_toilet` | Toilet soap including all kinds of bath soap (cakes) |
| `aerated_soft_drinks` | Aerated soft drinks, non-alcoholic |
| `mineral_water` | Mineral water and drinking water |
| `cement` | Cement in bags |
| `paint_varnish` | Paint (other than paste paint or solid paint), varnish, varnish stains, enamels |
| `paste_solid_paint` | Paste paint and solid paint |
| `base_paint` | Base paint |
| `soap_any` | (Third Schedule) All kinds of soaps |
| `lotions` | (Third Schedule) Lotions |
| `cream_non_milk` | (Third Schedule) Cream (other than cream of milk) |
| Fourth Schedule keys | aerosol_products, acids_liquid, compressed_liquefied_gas, curd, electric_cables, electric_wire, fencing_wire, fruits_all_kinds, furnace_oil, non_edible_vegetable_oil, edible_oil_vanaspati_ghee_butter, heavy_residual_fuel_oil, industrial_diesel_fuel, honey_malt_extract_syrup, ice_cream_frozen_products, liquid_chemicals, liquefied_petroleum_gas, nails_wood_screws, paints_varnish_enamels, paste_solid_paint, rasgulla_gulab_jamun_sweets, ready_made_garments, sauces_all_kinds, tyres_and_tubes, yarn, cosmetics_creams_shampoo_lotions_perfumes |

## Procedure for amendments

1. Open the PDF and locate the row (note the page number).
2. Transcribe exactly — do not normalize, round, or "fix" values.
3. Update the row in `app/rules/schedule_data.py` with `source_page` set.
4. Extend or adjust the pin test in `tests/test_rules.py` (one transcribed
   value per table), so transcription regressions are caught.
5. Run `pytest tests/ -q`.

## What activates with verified data

- **Rule 7-B** compares supplied `estimated_letter_heights_mm.net_quantity`
  against the applicable verified table (weight/volume bands, or PDP-area
  bands when quantity is declared by length/area/number; column selected by
  `package.is_formed_container`).
- **Rule 11/12** consult Third/Fourth Schedule flags for "when packed" and
  Rule 12(2) exceptions (category-known lookups).
- **Second-Schedule quantity checks** (future phase) read the specified
  quantities directly from the data.
