"""Structured schedule data for the LMPC 2011 rules.

All numeric legal values (First Schedule MPE tables, Rule 7 letter-height
tables, Second Schedule specified quantities, Third/Fourth Schedule lists)
live HERE — never scattered through evaluator code. Every row carries
`verified` and `source_page`: a row is populated only after being read and
checked against the supplied PDF (procedure in docs/schedule-population.md).
Unverified data can never drive a COMPLIANT/VIOLATION decision — evaluators
return NOT_VERIFIABLE instead, which is why the flags are enforced here.

Source: Legal Metrology (Packaged Commodities) Rules, 2011 — supplied PDF
(repo copy: legal-engine/docs/lmpc-2011.pdf, 83-page scan without a text
layer). Values below were transcribed from page renders read by two
independent OCR engines (Tesseract via the computer-vision container and
Windows.Media.Ocr) at 200–900 dpi plus positional cell analysis; cells whose
reads conflicted were settled by explicit human transcription (First Schedule
Table I percentage column, Second Schedule rows 1–5). First Schedule Table II
(length/area/number MPE) resisted every OCR technique and is recorded
UNVERIFIED with its textual structure only.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MpeRow:
    """One First Schedule maximum-permissible-error band."""

    min_quantity: float | None  # inclusive lower bound (None = unbounded)
    max_quantity: float | None  # inclusive upper bound (None = unbounded)
    unit: str  # "g" | "ml" (per the schedule's own unit column)
    mpe_fraction: float | None  # fractional MPE (e.g. 0.03)
    mpe_absolute: float | None  # absolute MPE in the row's unit
    source_page: int | None
    verified: bool = False


@dataclass(frozen=True)
class LetterHeightRow:
    """One row of a Rule 7 minimum-letter-height table."""

    min_quantity: float | None
    max_quantity: float | None
    min_height_mm: float
    source_page: int | None
    verified: bool = False


@dataclass(frozen=True)
class LetterHeightTable:
    """Table I (normal containers) or Table II (formed containers), Rule 7."""

    name: str
    applies_to_formed: bool
    rows: list[LetterHeightRow] = field(default_factory=list)
    source_page: int | None = None
    verified: bool = False


@dataclass(frozen=True)
class SecondScheduleEntry:
    """One Second Schedule commodity: specified quantities for retail packs."""

    commodity: str
    category_key: str
    specified_quantities: list[dict] = field(default_factory=list)  # [{"value": ..., "unit": ...}]
    source_page: int | None = None
    verified: bool = False


@dataclass(frozen=True)
class ScheduleFlag:
    """One Third/Fourth Schedule entry (when-packed allowance / Rule 12(2)
    exceptions), keyed by commodity category."""

    category_key: str
    detail: str
    source_page: int | None
    verified: bool = False


# --------------------------------------------------------------------------
# First Schedule — Maximum Permissible Error (PDF pages 72–73)
# --------------------------------------------------------------------------
# Table I: net quantities declared by weight or volume. The percentage column
# was human-transcribed (OCR-conflicted cells); all nine rows cross-check
# across the 200 dpi full-page read, 900 dpi cell reads, and the transcript.
# Each band applies to both g and ml ("g or ml" unit column), so every band
# is registered once per unit with the same numbers.

_FIRST_SCHEDULE_BANDS: tuple[tuple[float | None, float | None, float | None, float | None], ...] = (
    # (min, max, mpe_fraction, mpe_absolute) — Table I, page 72
    (None, 50.0, 0.09, None),      # (i)   up to 50            -> 9%
    (50.0, 100.0, 0.045, None),    # (ii)  50 to 100           -> 4.5%
    (100.0, 200.0, 0.045, None),   # (iii) 100 to 200          -> 4.5%
    (200.0, 300.0, None, 9.0),     # (iv)  200 to 300          -> 9 g (pct column "—")
    (300.0, 500.0, 0.03, None),    # (v)   300 to 500          -> 3%
    (500.0, 1000.0, 0.015, None),  # (vi)  500 to 1000         -> 1.5%
    (1000.0, 10000.0, 0.015, None),  # (vii) 1000 to 10000     -> 1.5%
    (10000.0, 15000.0, None, 150.0),  # (viii) 10000 to 15000 -> 150 g (pct column "—")
    (15000.0, None, 0.01, None),   # (ix)  more than 15000     -> 1.0%
)

FIRST_SCHEDULE_MPE: list[MpeRow] = [
    MpeRow(min_q, max_q, unit, frac, absolute, source_page=72, verified=True)
    for min_q, max_q, frac, absolute in _FIRST_SCHEDULE_BANDS
    for unit in ("g", "ml")
]

# NOTE (unverified): First Schedule Table II (page 73) — MPE on quantities
# declared by length, area or number — is recorded here as text only because
# its numeric column could not be reliably read from the scan:
#   (i)   in units of length: <UNVERIFIED>% of declared quantity up to 10 m,
#         thereafter <UNVERIFIED>%
#   (ii)  in units of area: <UNVERIFIED>% up to 10 sq. metre, thereafter
#         <UNVERIFIED>%
#   (iii) by number: <UNVERIFIED>% of declared quantity
# Do NOT guess these values; transcribe them per docs/schedule-population.md
# to activate any future rule that needs them.

# Rule 7 — minimum height of numerals. Table I bands by net quantity declared
# by weight or volume (g / ml); Table II bands by the area of the principal
# display panel in cm² (for quantities declared by length/area/number).
# Columns: normal container vs blown/formed/moulded/embossed/perforated.

_R7_TABLE_I_BANDS: tuple[tuple[float | None, float | None, float, float], ...] = (
    # (min, max, normal_mm, formed_mm) — Rule 7 Table I, page 47
    (None, 200.0, 1.0, 2.0),  # up to 200 g/ml
    (200.0, 500.0, 2.0, 4.0),  # above 200 and up to 500 g/ml
    (500.0, None, 4.0, 6.0),  # above 500 g/ml
)

_R7_TABLE_II_BANDS: tuple[tuple[float | None, float | None, float, float], ...] = (
    # (min, max, normal_mm, formed_mm) — Rule 7 Table II, page 48 (cm² of PDP)
    (None, 100.0, 1.0, 2.0),      # up to 100 cm²
    (100.0, 500.0, 2.0, 4.0),     # above 100 and up to 500 cm²
    (500.0, 2500.0, 4.0, 6.0),    # above 500 and up to 2500 cm²
    (2500.0, None, 6.0, 6.0),     # above 2500 cm²
)


LETTER_HEIGHT_TABLE_NORMAL = LetterHeightTable(
    name="Rule 7 Table I — minimum height of numerals, normal containers (net quantity by weight/volume)",
    applies_to_formed=False,
    rows=[
        LetterHeightRow(lo, hi, normal_mm, source_page=47, verified=True)
        for lo, hi, normal_mm, _formed in _R7_TABLE_I_BANDS
    ],
    source_page=47,
    verified=True,
)
LETTER_HEIGHT_TABLE_FORMED = LetterHeightTable(
    name="Rule 7 Table I — minimum height of numerals, blown/formed/moulded/embossed/perforated containers",
    applies_to_formed=True,
    rows=[
        LetterHeightRow(lo, hi, formed_mm, source_page=47, verified=True)
        for lo, hi, _normal, formed_mm in _R7_TABLE_I_BANDS
    ],
    source_page=47,
    verified=True,
)

# Table II (area of principal display panel) — same normal/formed split.
LETTER_HEIGHT_TABLE_NORMAL_AREA = LetterHeightTable(
    name="Rule 7 Table II — minimum height of numerals, normal containers (net quantity by length/area/number; bands in cm² of PDP)",
    applies_to_formed=False,
    rows=[
        LetterHeightRow(lo, hi, normal_mm, source_page=48, verified=True)
        for lo, hi, normal_mm, _formed in _R7_TABLE_II_BANDS
    ],
    source_page=48,
    verified=True,
)
LETTER_HEIGHT_TABLE_FORMED_AREA = LetterHeightTable(
    name="Rule 7 Table II — minimum height of numerals, blown/formed/moulded/embossed/perforated containers (bands in cm² of PDP)",
    applies_to_formed=True,
    rows=[
        LetterHeightRow(lo, hi, formed_mm, source_page=48, verified=True)
        for lo, hi, _normal, formed_mm in _R7_TABLE_II_BANDS
    ],
    source_page=48,
    verified=True,
)

# --------------------------------------------------------------------------
# Second Schedule — commodities and specified standard quantities (pages 73–75)
# --------------------------------------------------------------------------

def _q(*pairs: tuple[float, str]) -> list[dict]:
    return [{"value": v, "unit": u} for v, u in pairs]


SECOND_SCHEDULE: list[SecondScheduleEntry] = [
    SecondScheduleEntry(
        "Baby food",
        "baby_food",
        _q((25, "g"), (50, "g"), (75, "g"), (100, "g"), (150, "g"), (200, "g"), (250, "g"), (300, "g")),
        source_page=73,
        verified=True,
    ),
    SecondScheduleEntry(
        "Weaning food",
        "weaning_food",
        _q(
            (100, "g"), (200, "g"), (300, "g"), (400, "g"), (500, "g"), (600, "g"),
            (700, "g"), (800, "g"), (900, "g"), (1, "kg"), (2, "kg"), (5, "kg"), (10, "kg"),
        ),
        source_page=73,
        verified=True,
    ),
    SecondScheduleEntry(
        "Biscuits",
        "biscuits",
        _q((600, "g"), (700, "g"), (800, "g"), (900, "g"), (1, "kg"), (2, "kg"), (5, "kg"), (10, "kg")),
        source_page=73,
        verified=True,
    ),
    SecondScheduleEntry(
        "Bread including brown bread but excluding bun",
        "bread",
        _q((100, "g")),
        source_page=73,
        verified=True,
    ),
    SecondScheduleEntry(
        "Un-canned packages of butter and margarine",
        "butter_margarine",
        _q((25, "g"), (50, "g"), (100, "g"), (200, "g"), (500, "g"), (1, "kg"), (2, "kg"), (5, "kg")),
        source_page=73,
        verified=True,
    ),
    SecondScheduleEntry(
        "Cereals and Pulses",
        "cereals_pulses",
        _q((100, "g"), (200, "g"), (500, "g"), (1, "kg"), (2, "kg"), (5, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Coffee",
        "coffee",
        _q((25, "g"), (50, "g"), (100, "g"), (200, "g"), (250, "g"), (500, "g"), (1, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Tea",
        "tea",
        _q((25, "g"), (50, "g"), (100, "g"), (125, "g"), (250, "g"), (500, "g"), (1, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Materials which may be constituted or reconstituted as beverages",
        "beverage_mixes",
        _q((25, "g"), (50, "g"), (100, "g"), (125, "g"), (200, "g"), (500, "g"), (1, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Edible Oils, Vanaspati, ghee, butter oil",
        "edible_oils",
        _q((50, "g"), (100, "g"), (200, "g"), (500, "g"), (1, "kg"), (2, "kg"), (3, "kg"), (5, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Milk powder",
        "milk_powder",
        _q((50, "g"), (100, "g"), (200, "g"), (500, "g"), (1, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Non-soapy detergents (powder)",
        "detergent_powder",
        _q((50, "g"), (100, "g"), (200, "g"), (500, "g"), (700, "g"), (1, "kg"), (1.5, "kg"), (2, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Atta, rawa and suji",
        "atta_rawa_suji",
        _q((100, "g"), (200, "g"), (500, "g"), (1, "kg"), (2, "kg"), (5, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Salt",
        "salt",
        _q((50, "g"), (100, "g"), (200, "g"), (500, "g"), (750, "g"), (1, "kg"), (2, "kg"), (5, "kg")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Laundry soap",
        "soap_laundry",
        _q((50, "g"), (75, "g"), (100, "g")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Non-soapy detergent cakes/bars",
        "soap_non_soapy_cakes",
        _q((50, "g"), (75, "g"), (100, "g"), (125, "g"), (150, "g"), (200, "g"), (250, "g"), (300, "g")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Toilet soap including all kinds of bath soap (cakes)",
        "soap_toilet",
        _q((25, "g"), (50, "g"), (75, "g"), (100, "g"), (125, "g"), (150, "g")),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Aerated soft drinks, non-alcoholic",
        "aerated_soft_drinks",
        _q(
            (65, "ml"), (100, "ml"), (125, "ml"), (150, "ml"), (200, "ml"), (250, "ml"),
            (300, "ml"), (330, "ml"), (500, "ml"), (750, "ml"), (1, "litre"),
            (1.5, "litre"), (2, "litre"), (3, "litre"), (4, "litre"), (5, "litre"),
        ),
        source_page=74,
        verified=True,
    ),
    SecondScheduleEntry(
        "Mineral water and drinking water",
        "mineral_water",
        _q(
            (100, "ml"), (150, "ml"), (200, "ml"), (250, "ml"), (300, "ml"), (500, "ml"),
            (750, "ml"), (1, "litre"), (1.5, "litre"), (2, "litre"), (3, "litre"),
            (4, "litre"), (5, "litre"),
        ),
        source_page=75,
        verified=True,
    ),
    SecondScheduleEntry(
        "Cement in bags",
        "cement",
        _q((1, "kg"), (2, "kg"), (5, "kg"), (10, "kg"), (20, "kg"), (25, "kg"), (40, "kg"), (50, "kg")),
        source_page=75,
        verified=True,
    ),
    SecondScheduleEntry(
        "Paint (other than paste paint or solid paint), varnish, varnish stains, enamels",
        "paint_varnish",
        _q(
            (50, "ml"), (100, "ml"), (200, "ml"), (500, "ml"), (1, "litre"), (2, "litre"),
            (3, "litre"), (4, "litre"), (5, "litre"),
        ),
        source_page=75,
        verified=True,
    ),
    SecondScheduleEntry(
        "Paste paint and solid paint",
        "paste_solid_paint",
        _q((500, "g"), (1, "kg"), (1.5, "kg"), (2, "kg"), (3, "kg"), (5, "kg"), (7, "kg")),
        source_page=75,
        verified=True,
    ),
    SecondScheduleEntry(
        "Base paint",
        "base_paint",
        _q(
            (450, "ml"), (500, "ml"), (900, "ml"), (925, "ml"), (950, "ml"), (975, "ml"),
            (1, "litre"), (3.6, "litre"), (3.7, "litre"), (3.8, "litre"), (3.9, "litre"), (4, "litre"),
        ),
        source_page=75,
        verified=True,
    ),
]

# Third Schedule — commodities whose quantity declaration may be qualified by
# the words "when packed" (page 75).
THIRD_SCHEDULE: list[ScheduleFlag] = [
    ScheduleFlag("soap_any", "All kinds of soaps", source_page=75, verified=True),
    ScheduleFlag("lotions", "Lotions", source_page=75, verified=True),
    ScheduleFlag("cream_non_milk", "Cream (other than cream of milk)", source_page=75, verified=True),
]

# Fourth Schedule — exceptions referred to in Rule 12(2): the terms in which
# the quantity declaration may be expressed (pages 75–76).
FOURTH_SCHEDULE: list[ScheduleFlag] = [
    ScheduleFlag("aerosol_products", "Weight", source_page=75, verified=True),
    ScheduleFlag("acids_liquid", "Weight or volume", source_page=75, verified=True),
    ScheduleFlag("compressed_liquefied_gas", "Weight and equivalent volume at stated temperature and pressure", source_page=75, verified=True),
    ScheduleFlag("curd", "Weight", source_page=76, verified=True),
    ScheduleFlag("electric_cables", "Length or weight", source_page=76, verified=True),
    ScheduleFlag("electric_wire", "Length or weight", source_page=76, verified=True),
    ScheduleFlag("fencing_wire", "Number or weight", source_page=76, verified=True),
    ScheduleFlag("fruits_all_kinds", "Number or weight", source_page=76, verified=True),
    ScheduleFlag("furnace_oil", "Weight or volume", source_page=76, verified=True),
    ScheduleFlag("non_edible_vegetable_oil", "Weight or volume", source_page=76, verified=True),
    ScheduleFlag("edible_oil_vanaspati_ghee_butter", "Weight or volume", source_page=76, verified=True),
    ScheduleFlag("heavy_residual_fuel_oil", "Weight", source_page=76, verified=True),
    ScheduleFlag("industrial_diesel_fuel", "Volume", source_page=76, verified=True),
    ScheduleFlag("honey_malt_extract_syrup", "Weight", source_page=76, verified=True),
    ScheduleFlag("ice_cream_frozen_products", "Volume", source_page=76, verified=True),
    ScheduleFlag("liquid_chemicals", "Weight or volume", source_page=76, verified=True),
    ScheduleFlag("liquefied_petroleum_gas", "Weight", source_page=76, verified=True),
    ScheduleFlag("nails_wood_screws", "Number or weight", source_page=76, verified=True),
    ScheduleFlag("paints_varnish_enamels", "Volume", source_page=76, verified=True),
    ScheduleFlag("paste_solid_paint", "Weight", source_page=76, verified=True),
    ScheduleFlag("rasgulla_gulab_jamun_sweets", "Weight", source_page=76, verified=True),
    ScheduleFlag("ready_made_garments", "Number", source_page=76, verified=True),
    ScheduleFlag("sauces_all_kinds", "Weight", source_page=76, verified=True),
    ScheduleFlag("tyres_and_tubes", "Weight or length of yarn", source_page=76, verified=True),
    ScheduleFlag("yarn", "Weight", source_page=76, verified=True),
    ScheduleFlag("cosmetics_creams_shampoo_lotions_perfumes", "Weight or measure", source_page=76, verified=True),
]


def mpe_for(declared_quantity: float, unit: str) -> MpeRow | None:
    """The verified MPE row covering a declared quantity, or None.

    Returns None both when no row matches and when no rows are verified —
    callers cannot distinguish, and must treat None as not-verifiable.
    """
    for row in FIRST_SCHEDULE_MPE:
        if not row.verified or row.unit != unit:
            continue
        if (row.min_quantity is None or declared_quantity >= row.min_quantity) and (
            row.max_quantity is None or declared_quantity <= row.max_quantity
        ):
            return row
    return None


def letter_height_table(is_formed_container: bool, by_pdp_area: bool = False) -> LetterHeightTable:
    if by_pdp_area:
        return LETTER_HEIGHT_TABLE_FORMED_AREA if is_formed_container else LETTER_HEIGHT_TABLE_NORMAL_AREA
    return LETTER_HEIGHT_TABLE_FORMED if is_formed_container else LETTER_HEIGHT_TABLE_NORMAL


def second_schedule_entry(category_key: str) -> SecondScheduleEntry | None:
    for entry in SECOND_SCHEDULE:
        if entry.verified and entry.category_key == category_key:
            return entry
    return None


def third_schedule_flag(category_key: str) -> ScheduleFlag | None:
    for flag in THIRD_SCHEDULE:
        if flag.verified and flag.category_key == category_key:
            return flag
    return None


def fourth_schedule_flag(category_key: str) -> ScheduleFlag | None:
    for flag in FOURTH_SCHEDULE:
        if flag.verified and flag.category_key == category_key:
            return flag
    return None
