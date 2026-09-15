"""Structured schedule data for the LMPC 2011 rules.

All numeric legal values (First Schedule MPE tables, Rule 7 letter-height
tables, Second Schedule specified quantities, Third/Fourth Schedule lists)
live HERE — never scattered through evaluator code. Every row carries
`verified` and `source_page`: a row is populated only after being read and
checked against the supplied PDF (procedure in docs/schedule-population.md).
Unverified data can never drive a COMPLIANT/VIOLATION decision — evaluators
return NOT_VERIFIABLE instead, which is why the flags are enforced here.

The supplied PDF was not present in this environment at build time, so every
dataset below ships EMPTY and unverified. Dropping in the PDF and following
the documented population procedure activates the dependent checks without
any evaluator changes.
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
# First Schedule — Maximum Permissible Error (data-driven, currently empty)
# --------------------------------------------------------------------------
FIRST_SCHEDULE_MPE: list[MpeRow] = []

LETTER_HEIGHT_TABLE_NORMAL = LetterHeightTable(
    name="Rule 7 — minimum height of numerals (normal containers)", applies_to_formed=False
)
LETTER_HEIGHT_TABLE_FORMED = LetterHeightTable(
    name="Rule 7 — minimum height of numerals (blown/formed/moulded/embossed/perforated containers)",
    applies_to_formed=True,
)

# --------------------------------------------------------------------------
# Second Schedule — commodities and specified standard quantities (empty)
# --------------------------------------------------------------------------
SECOND_SCHEDULE: list[SecondScheduleEntry] = []

# Third Schedule — commodities where "when packed" / "when packed" variants
# may be used (empty until populated from the PDF).
THIRD_SCHEDULE: list[ScheduleFlag] = []

# Fourth Schedule — exceptions to Rule 12(2) (empty until populated).
FOURTH_SCHEDULE: list[ScheduleFlag] = []


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


def letter_height_table(is_formed_container: bool) -> LetterHeightTable:
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
