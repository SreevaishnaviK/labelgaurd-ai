"""Deterministic field extraction from OCR blocks — spatial, Phase 9A.

Rule-based, no network, no LLM. Every candidate trace must reference real OCR
block IDs; nothing is invented. Ambiguity is reported, never silently resolved.

Phase 9A: extraction is anchored in GEOMETRY. OCR blocks are first
reconstructed into visual lines and reading order (app.extraction.spatial —
engine line numbers are unreliable on multi-column labels), then every field
is extracted from an ANCHOR's spatial neighborhood (its own line, lines below
in the same column, side-by-side lines) — never from a flat scan of the whole
document. This is what keeps the nutrition table out of the ingredients, the
address out of the company name, and "Use By" out of the batch number.

Regex is still used — but only INSIDE the correct candidate region.

Confidence: the configured deterministic confidence reflects same-line,
strongly-anchored reads; reads joined across blocks (value below the anchor,
wrapped declarations) are context-derived and carry the lower multi-block
confidence. OCR confidence stays separate.
"""
import re
from dataclasses import dataclass, field

from app.config import get_settings
from app.extraction import normalization as norm
from app.extraction import spatial
from app.extraction.base import BaseFieldExtractor, FIELD_NAMES
from app.schemas.extraction import (
    EvidenceRef,
    ExtractedFieldOut,
    FieldCandidate,
    OCRBlockIn,
    OCRPageIn,
)
from app.extraction.spatial import VisualLine

# ---------------------------------------------------------------- patterns

_MONEY_TOKEN = r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
_MONEY_BARE = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
_MRP_INDICATOR = r"m\.?r\.?p|maximum\s+retail\s+price"
# One amount pattern, ONE capture group: an alternation of currency-prefixed
# and bare branches would renumber the group depending on which branch the
# regex engine lands on after backtracking ("MRP Rs. 68" used to yield a
# None group(1) that way).
_MONEY_BODY = r"[0-9][0-9,]*(?:\.[0-9]{1,2})?"
_MONEY_ANY_RE = re.compile(rf"(?:₹|rs\.?|inr)?\s*({_MONEY_BODY})", re.IGNORECASE)
# Same line: indicator, optional stray glyphs (the ₹ symbol is often OCR'd as
# % or $), then the amount.
_MRP_LINE_RE = re.compile(
    rf"\b(?:{_MRP_INDICATOR})\b[^0-9\n]{{0,12}}{_MONEY_ANY_RE.pattern}",
    re.IGNORECASE,
)
_MONEY_GROUP_RE = re.compile(_MONEY_ANY_RE.pattern + r"\s*$", re.IGNORECASE)

_NET_LINE_RE = re.compile(
    r"\b(?:net\s+(?:qty|quantity|wt\.?|weight)|contents)\b\s*[:.\-]?",
    re.IGNORECASE,
)
_UNIT_TOKEN = r"(?:mg|g|gm|gms|kgs?|ml|l|ltr|litres?|liters?)"
_UNIT_VALUE_RE = re.compile(
    rf"([0-9]+(?:\.[0-9]+)?)\s*({_UNIT_TOKEN})\b\.?", re.IGNORECASE
)

# Dates: numeric forms plus "15 MAY 2024" month-name forms ("NOV2024" — OCR
# drops the space — must still match).
_MONTH_DATE = (
    r"(?P<date>"
    r"[0-9]{1,2}\s*[A-Za-z]{3,9}\.?\s*[0-9]{2,4}"
    r"|[0-9]{1,2}[./-][0-9]{2,4}(?:[./-][0-9]{2,4})?"
    r"|[0-9]{2,4}[./-][0-9]{2,4}"
    r")"
)
_DATE_FIELDS = [
    ("manufacturing_date", r"\b(?:manufacturing\s+date|(?:mfg|mfd)\.?\s+date|mfd|mfg|manufactured(?:\s+on)?)\b"),
    ("packing_date", r"\b(?:packing\s+date|pkd\.?\s+date|pkd|packed(?:\s+on)?)\b"),
    ("best_before", r"\bbest\s+before\b"),
    ("use_by", r"\buse\s+before\b|\buse[\s.]*by\b"),
    ("expiry_date", r"\bexpiry(?:\s+date)?\b|\bexp\b"),
]
# _DATE_LINE_TEMPLATE is never .format()-ed: the date pattern contains regex
# quantifiers like {2,4} that str.format would eat. Compose by concatenation.
# "Mfg: Date: 15 MAY 2024" — the label word DATE repeats after the anchor;
# allow one such filler between indicator and value.
_DATE_LINE_PREFIX = r"(?:{})\s*[:.\-]?\s*(?:(?:date|dt)\b\s*[:.\-]?\s*)?"  # .format() THIS part alone (no quantifiers)
_DATE_LINE_SUFFIX = _MONTH_DATE + "\.?\)?"
_FULL_DATE_RE = re.compile(rf"{_MONTH_DATE}\.?\)?", re.IGNORECASE)

_PHONE_ANCHOR_RE = re.compile(
    r"(?:consumer\s+care|consumer\s+complaints|customer\s+care|customer\s+service"
    r"|toll\s*free|helpline|contact\s+us)",
    re.IGNORECASE,
)
# Same-line contact capture: the value follows the indicator after a separator.
_CONTACT_CAPTURE_RE = re.compile(
    rf"({_PHONE_ANCHOR_RE.pattern})[:\s]*([^\n]{{4,60}})",
    re.IGNORECASE,
)
# A capture that is itself just the next label word is not a value.
_CONTACT_LABEL_RE = re.compile(
    r"^(?:consumer\s+care|consumer\s+complaints|customer\s+care|customer\s+service"
    r"|toll\s*free|helpline|contact(?:\s+us)?|call|email|or|at|executive)$",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_ROLES = {
    "manufacturer": (
        r"\bmanufactured\s*(?:&|and)\s*(?:packed|marketed)?\s*by\b"
        r"|\bmanufactured\s+by\b|\bmfd\.?\s+by\b|\bmfg\.?\s+by\b"
    ),
    "packer": (
        r"\b(?:manufactured\s*(?:&|and)\s*packed|packed\s*(?:&|and)\s*marketed|packed)\s+by\b"
        r"|\bpkt\.?\s+by\b"
    ),
    "importer": r"\b(?:imported\s+by|importer)\b[:\s]*",
    # Standalone "Marketed by" only: combined forms ("Packed & Marketed by",
    # "Manufactured and Marketed by") belong to packer/manufacturer, so the
    # lookbehind excludes a preceding "& " / "and ".
    "marketer": r"(?<!&\s)(?<!and\s)\bmarketed\s+by\b",
}
_ROLE_RES = {role: re.compile(pattern, re.IGNORECASE) for role, pattern in _ROLES.items()}

# A line that looks like an address rather than a company name: digits
# (plot/house/PIN numbers), commas, or common Indian address words.
_ADDRESS_LINE_RE = re.compile(
    r"\d|,|\b(?:plot|street|road|nagar|colony|sector|industrial|estate|layout|"
    r"floor|building|avenue|marg|highway|village|taluk|district|pin)\b",
    re.IGNORECASE,
)
_COUNTRY_RES = [
    re.compile(r"\bcountry\s+of\s+origin\b\s*:?\s*([A-Za-z][A-Za-z\s]{2,40})", re.IGNORECASE),
    re.compile(r"\bmade\s+in\s+([A-Za-z][A-Za-z\s]{2,40})", re.IGNORECASE),
    re.compile(r"\bproduct\s+of\s+([A-Za-z][A-Za-z\s]{2,40})", re.IGNORECASE),
]
_INGREDIENTS_RE = re.compile(r"\bingredients?\b\s*[:\-]?", re.IGNORECASE)
_INGREDIENT_ANCHOR_TOLERANCE = 40  # px: ingredient lines share the anchor's column


def _normalize_date(raw: str) -> str:
    """Deterministic date cleanup: 'NOV.2024' -> 'NOV 2024' (letter-dot-digit
    is an OCR punctuation artifact; numeric separators like 12.08.2025 are
    real and untouched)."""
    value = raw.strip(" .,;:)]}")
    value = re.sub(r"(?<=[A-Za-z])\.(?=[0-9])", " ", value)
    return re.sub(r"\s+", " ", value).strip()
# §18: the one ingredient-context correction that is deterministic and safe.
_INGREDIENT_FIXES = [(re.compile(r"\blodised\b", re.IGNORECASE), "Iodised")]
_VEG_RE = re.compile(r"\bnon[\s-]?veg(?:etarian)?\b|\bveg(?:etarian)?\b", re.IGNORECASE)

# Blocks that must never be picked as the product name.
_RESERVED_RE = re.compile(
    r"\b(?:mrp|m\.r\.p|maximum\s+retail|net\s+(?:qty|quantity|wt|weight)|contents|"
    r"manufactured|packed|marketed|imported|importer|batch|lot\s*no|mfd|mfg|pkd|"
    r"best\s+before|use\s+by|exp|expiry|consumer\s+care|customer\s+care|helpline|"
    r"toll\s*free|ingredients|country\s+of\s+origin|made\s+in|www\.|@|"
    r"non[\s-]?vegg?(?:etarian)?\b|\bvegg?(?:etarian)?\b)",
    re.IGNORECASE,
)


@dataclass
class Trace:
    """One extractor's observation: normalized value + supporting blocks."""

    value: dict
    blocks: list[OCRBlockIn] = field(default_factory=list)
    raw_text: str = ""


def _looks_like_address_line(text: str) -> bool:
    return bool(_ADDRESS_LINE_RE.search(text))


def _address_join(parts: list[str]) -> str:
    """Join address parts with commas/spaces; a segment glued to the next by
    OCR ("201306; India.") gets its separator normalized deterministically."""
    joined = " ".join(part.strip() for part in parts if part.strip())
    joined = re.sub(r"\s+,", ",", joined)
    joined = re.sub(r",{2,}", ",", joined)
    # "- 201306; India." — the semicolon is an OCR artifact after a PIN code.
    joined = re.sub(r"(?<=[0-9]);\s*", ", ", joined)
    return re.sub(r"\s{2,}", " ", joined).strip()


def _dedup(blocks: list[OCRBlockIn]) -> list[OCRBlockIn]:
    """Order-preserving dedupe by identity (pydantic models are unhashable)."""
    seen: set[int] = set()
    unique: list[OCRBlockIn] = []
    for block in blocks:
        if id(block) not in seen:
            seen.add(id(block))
            unique.append(block)
    return unique


def _evidence(blocks: list[OCRBlockIn]) -> list[EvidenceRef]:
    return [EvidenceRef(ocr_block_id=b.id, page_number=b.page_number) for b in blocks]


def _ocr_confidence(blocks: list[OCRBlockIn]) -> float | None:
    if not blocks:
        return None
    return round(sum(b.confidence for b in blocks) / len(blocks), 1)


def _field(
    name: str,
    traces: list[Trace],
    extraction_confidence: float | None = None,
) -> ExtractedFieldOut:
    """Build one field output from candidate traces.

    Exactly one trace -> detected. Multiple distinct values -> ambiguous with
    all candidates surfaced (never silently resolved). Zero -> not_detected.
    """
    if not traces:
        return ExtractedFieldOut(field_name=name, status="not_detected")
    distinct = {repr(t.value) for t in traces}
    if len(distinct) > 1:
        return ExtractedFieldOut(
            field_name=name,
            status="ambiguous",
            value=None,
            extraction_confidence=extraction_confidence,
            candidates=[
                FieldCandidate(
                    raw_text=t.raw_text or " ".join(b.text for b in t.blocks),
                    value=t.value,
                    method="deterministic",
                    confidence=extraction_confidence,
                    evidence=_evidence(t.blocks),
                )
                for t in traces
            ],
            evidence=_evidence([b for t in traces for b in t.blocks]),
        )
    trace = traces[0]
    blocks = trace.blocks
    return ExtractedFieldOut(
        field_name=name,
        status="detected",
        value=trace.value,
        raw_text=trace.raw_text or None,
        ocr_confidence=_ocr_confidence(blocks),
        extraction_confidence=extraction_confidence,
        evidence=_evidence(blocks),
    )


def _clean_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


class DeterministicFieldExtractor(BaseFieldExtractor):
    """Anchored, spatially-aware rule extraction: indicators + neighborhoods."""

    name = "deterministic"

    # -------------------------------------------------- per-field extractors

    def _extract_mrp(self, lines: list[VisualLine]) -> list[Trace]:
        traces = []
        indicator_re = re.compile(_MRP_INDICATOR, re.IGNORECASE)
        for line, _match in spatial.find_anchor(lines, indicator_re):
            matched = False
            for amount_match in _MRP_LINE_RE.finditer(line.text):
                amount = _MONEY_GROUP_RE.search(amount_match.group().rstrip(".,;:"))
                if amount:
                    traces.append(
                        Trace(
                            value={"amount": _clean_amount(amount.group(1)), "currency": "INR"},
                            blocks=line.blocks,
                            raw_text=amount_match.group().strip(),
                        )
                    )
                    matched = True
            if not matched:
                # Indicator alone: the amount sits below in the same column —
                # never elsewhere in the document.
                for follower in spatial.neighborhood(lines, line, below=2)[1:]:
                    follower_match = _MONEY_ANY_RE.fullmatch(
                        follower.text.strip().rstrip(".,;:")
                    )
                    if follower_match:
                        traces.append(
                            Trace(
                                value={
                                    "amount": _clean_amount(follower_match.group(1)),
                                    "currency": "INR",
                                },
                                blocks=[*line.blocks, *follower.blocks],
                                raw_text=f"{line.text.strip()} {follower.text.strip()}",
                            )
                        )
                    break
        return traces

    def _extract_net_quantity(self, lines: list[VisualLine]) -> list[Trace]:
        """Net quantity from the NET anchor's neighborhood: value on the same
        line after the indicator, else the block DIRECTLY BELOW the anchor
        block (multi-column lines can mix blocks, so the search is
        block-aware). Nutrition-table numbers live above/right and are never
        reachable."""
        traces = []
        for line, match in spatial.find_anchor(lines, _NET_LINE_RE):
            anchor_block = line.blocks[0]
            value_match = _UNIT_VALUE_RE.search(line.text[match.end() :]) or _UNIT_VALUE_RE.search(
                line.text
            )
            if value_match:
                normalized = norm.normalize_mass(
                    float(value_match.group(1)), value_match.group(2)
                ) or norm.normalize_volume(float(value_match.group(1)), value_match.group(2))
                if normalized:
                    traces.append(
                        Trace(
                            value={"value": normalized[0], "unit": normalized[1]},
                            blocks=line.blocks,
                            raw_text=value_match.group().strip(),
                        )
                    )
                continue
            # "Net Weight:" alone: the value block sits directly below in the
            # same column.
            value_line = None
            for follower in spatial.neighborhood(lines, line, below=2)[1:]:
                x0 = min((b.bbox or {}).get("x", 0) for b in follower.blocks)
                if x0 >= (anchor_block.bbox or {}).get("x", 0) + (anchor_block.bbox or {}).get(
                    "width", 0
                ) + 40:
                    continue  # side column, keep scanning down
                for block in follower.blocks:
                    m = _UNIT_VALUE_RE.fullmatch(block.text.strip())
                    if m:
                        normalized = norm.normalize_mass(float(m.group(1)), m.group(2)) or norm.normalize_volume(
                            float(m.group(1)), m.group(2)
                        )
                        if normalized:
                            traces.append(
                                Trace(
                                    value={"value": normalized[0], "unit": normalized[1]},
                                    blocks=[anchor_block, block],
                                    raw_text=f"{anchor_block.text.strip()} {block.text.strip()}",
                                )
                            )
                        value_line = follower
                        break
                if value_line is not None:
                    break
        return traces

    def _extract_product_name(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        """Prominence heuristic over geometry: the most visually dominant
        eligible block — glyph area × text length, with a 1.25× bonus in the
        top half of the eligible span (top/center label text is a name signal,
        not a hard filter). Adjacent prominent lines of the title stack
        (next block below within the band height, excluded region, no
        other content between) merge into one name.

        Eligibility: not reserved (MRP, net qty, roles, declarations, ...)
        and predominantly alphabetic (rejects codes and phone numbers).
        """
        eligible = [
            b
            for b in blocks
            if not _RESERVED_RE.search(b.text)
            and not _looks_like_address_line(b.text)
            and sum(ch.isalpha() for ch in b.text) >= 0.6 * max(len(b.text.strip()), 1)
        ]
        if not eligible:
            return []
        top_y = min((b.bbox or {}).get("y", 0) for b in eligible)
        max_bottom = max(
            (b.bbox or {}).get("y", 0) + (b.bbox or {}).get("height", 0) for b in eligible
        )
        midpoint = top_y + max(max_bottom - top_y, 1) * 0.5

        def dominance(b: OCRBlockIn) -> float:
            area = (b.bbox or {}).get("width", 0) * (b.bbox or {}).get("height", 0)
            position = 1.25 if (b.bbox or {}).get("y", 0) <= midpoint else 1.0
            return area * max(len(b.text.strip()), 1) * position

        best = max(eligible, key=dominance)
        words = best.text.strip()
        if not words or len(words) < 3:
            return []
        # Title-stack merge: same column, directly below the winner, not
        # reserved (subtitles like CLASSIC SALTED are eligible text).
        bb = best.bbox or {}
        merged_blocks = [best]
        for other in eligible:
            if other is best:
                continue
            ob = other.bbox or {}
            vertically_below = 0 <= ob.get("y", 0) - (bb.get("y", 0) + bb.get("height", 0)) <= max(
                int(bb.get("height", 40) * 0.6), 8
            )
            horizontally_aligned = (
                ob.get("x", 0) >= bb.get("x", 0) - 40
                and ob.get("x", 0) + ob.get("width", 0) <= bb.get("x", 0) + bb.get("width", 0) + 80
            )
            if vertically_below and horizontally_aligned:
                merged_blocks.append(other)
        merged_blocks.sort(key=lambda b: (b.bbox or {}).get("y", 0))
        name = " ".join(b.text.strip() for b in merged_blocks)
        return [Trace(value={"name": name}, blocks=merged_blocks, raw_text=name)]

    def _role_declarations(self, role: str, lines: list[VisualLine]) -> list[dict]:
        """Parse each role declaration into name vs address lines.

        Scanning is PER BLOCK: two declarations can share one visual line
        ("Packed by X" | "Imported by Y" side by side), so line-level
        association would steal the neighbor's name. The anchor block and its
        chained followers form the declaration region: plain segments are the
        company name, address-like segments (digits, commas, place words) are
        the address. Scanning stops at any other field indicator so nothing
        is double-counted — the address can never leak into the name.
        """
        rx = _ROLE_RES[role]
        other_res = [p for r, p in _ROLE_RES.items() if r != role]

        def _segments(text: str) -> list[str]:
            return [seg.strip(" :-—") for seg in text.splitlines() if seg.strip(" :-—")]

        def _stop(text: str) -> bool:
            return bool(_RESERVED_RE.search(text)) or any(p.search(text) for p in other_res)

        declarations = []
        for line in lines:
            for block_index, block in enumerate(line.blocks):
                match = rx.search(block.text)
                if not match:
                    continue
                name: list[str] = []
                address: list[str] = []
                name_blocks: list[OCRBlockIn] = [block]
                address_blocks: list[OCRBlockIn] = [block]

                def _classify(segments: list[str], blocks: list[OCRBlockIn]) -> bool:
                    """Fold segments into name/address. False => stop scanning."""
                    for seg in segments:
                        if _stop(seg):
                            return False
                        if _looks_like_address_line(seg):
                            address.append(seg)
                            address_blocks.extend(blocks)
                        elif not name and not address:
                            name.append(seg)
                            name_blocks.extend(blocks)
                        else:
                            return False
                    return True

                if not _classify(_segments(block.text[match.end() :]), []):
                    continue
                # Same-line neighbours (side-by-side declarations belong to
                # other roles and stop the scan via _stop()).
                for neighbour in line.blocks[block_index + 1 :]:
                    if _stop(neighbour.text) or not _classify(
                        _segments(neighbour.text), [neighbour]
                    ):
                        break
                # Lines below continue the declaration (address wraps).
                for follower in spatial.neighborhood(lines, line, below=3)[1:]:
                    if _stop(follower.text) or not _classify(
                        _segments(follower.text), follower.blocks
                    ):
                        break

                declarations.append(
                    {
                        "name": " ".join(name).strip(" ,-") or None,
                        "name_blocks": _dedup(name_blocks),
                        "address": address or None,
                        "address_blocks": _dedup(address_blocks),
                        # The name's evidence spans the whole declaration
                        # (spec: multi-block evidence for the company).
                        "all_blocks": _dedup([*name_blocks, *address_blocks]),
                    }
                )
        return declarations

    def _extract_role(self, role: str, lines: list[VisualLine]) -> list[Trace]:
        traces = []
        for declaration in self._role_declarations(role, lines):
            if declaration["name"]:
                traces.append(
                    Trace(
                        value={"name": declaration["name"]},
                        blocks=declaration["all_blocks"],
                        raw_text=declaration["name"],
                    )
                )
        return traces

    def _extract_role_address(self, role: str, lines: list[VisualLine]) -> list[Trace]:
        traces = []
        for declaration in self._role_declarations(role, lines):
            if declaration["address"]:
                joined = _address_join(declaration["address"])
                traces.append(
                    Trace(
                        value={"address": joined},
                        blocks=declaration["address_blocks"],
                        raw_text=joined,
                    )
                )
        return traces

    def _extract_dates(self, lines: list[VisualLine]) -> dict[str, list[Trace]]:
        found: dict[str, list[Trace]] = {}
        consumed: dict[int, set[int]] = {}
        for field_name, indicator in _DATE_FIELDS:
            pattern = re.compile(
                _DATE_LINE_PREFIX.format(indicator) + _DATE_LINE_SUFFIX, re.IGNORECASE
            )
            for line, match in spatial.find_anchor(lines, pattern):
                found.setdefault(field_name, []).append(
                    Trace(
                        value={"date": _normalize_date(match.group("date"))},
                        blocks=line.blocks,
                        raw_text=match.group().strip(),
                    )
                )
                consumed.setdefault(field_name, set()).add(id(line))
        # Indicator alone on its line: the date sits directly below in the
        # same column (fragmented labels).
        for field_name, indicator in _DATE_FIELDS:
            anchor_re = re.compile(indicator, re.IGNORECASE)
            for line, _match in spatial.find_anchor(lines, anchor_re):
                if id(line) in consumed.get(field_name, set()):
                    continue
                for follower in spatial.neighborhood(lines, line, below=1)[1:]:
                    follower_match = re.fullmatch(
                        _MONTH_DATE + r"\.?\)?", follower.text.strip(), re.IGNORECASE
                    )
                    if follower_match:
                        found.setdefault(field_name, []).append(
                            Trace(
                                value={"date": _normalize_date(follower_match.group("date"))},
                                blocks=[*line.blocks, *follower.blocks],
                                raw_text=f"{line.text.strip()} {follower.text.strip()}",
                            )
                        )
                    break
        return found

    def _extract_code(self, kind: str, word: str, lines: list[VisualLine]) -> list[Trace]:
        """Batch/lot codes: the value must be spatially associated with its
        own anchor — never borrowed from a label keyword or a quantity."""
        anchor_re = re.compile(rf"\b{word}\s*(?:no|number)?\b\s*[:.#\-]?\s*", re.IGNORECASE)
        traces = []
        for line, match in spatial.find_anchor(lines, anchor_re):
            candidate = line.text[match.end() :].strip(" :.#-")
            blocks = list(line.blocks)
            if not candidate or _RESERVED_RE.search(candidate) or candidate.isdigit():
                candidate = None
                for follower in spatial.neighborhood(lines, line, below=1)[1:]:
                    follower_candidate = follower.text.strip(" :.#-")
                    if (
                        _RESERVED_RE.search(follower_candidate)
                        or follower_candidate.isdigit()
                        or _UNIT_VALUE_RE.fullmatch(follower_candidate)
                    ):
                        break
                    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/\-_.]{2,30}", follower_candidate):
                        candidate = follower_candidate
                        blocks = [*line.blocks, *follower.blocks]
                    break
            if candidate:
                traces.append(
                    Trace(
                        value={"batch": candidate},
                        blocks=_dedup(blocks),
                        raw_text=f"{line.text[match.start() :].strip()} {candidate}".strip(),
                    )
                )
        return traces

    def _extract_contact(self, lines: list[VisualLine]) -> dict[str, list[Trace]]:
        """Phone/email only inside a consumer/customer-care section.

        The anchor line's neighborhood is the section; numbers elsewhere in
        the document are never consumer-care contacts.
        """
        found: dict[str, list[Trace]] = {}
        consumed_lines: set[int] = set()
        for line, _match in spatial.find_anchor(lines, _PHONE_ANCHOR_RE):
            if id(line) in consumed_lines:
                continue
            hood = spatial.neighborhood(lines, line, below=3)
            consumed_lines.update(id(member) for member in hood)
            hood_blocks = _dedup([b for member in hood for b in member.blocks])
            hood_text = " ".join(member.text for member in hood)

            phone = norm.normalize_phone(hood_text)
            if phone:
                found.setdefault("customer_care_phone", []).append(
                    Trace(value={"phone": phone}, blocks=hood_blocks, raw_text=line.text.strip())
                )
            email_match = _EMAIL_RE.search(hood_text)
            if email_match:
                found.setdefault("customer_care_email", []).append(
                    Trace(
                        value={"email": email_match.group().lower()},
                        blocks=hood_blocks,
                        raw_text=line.text.strip(),
                    )
                )

            # Human-readable contact line: same-line value after the
            # indicator, else the section's first line that is not itself an
            # indicator and not bare digits (those are the phone, already
            # captured as customer_care_phone).
            same_line = _CONTACT_CAPTURE_RE.search(line.text)
            contact = None
            if same_line:
                candidate = same_line.group(2).strip(" :;,.-—")
                if candidate and not _CONTACT_LABEL_RE.match(candidate):
                    contact = candidate
            if contact is None:
                for member in hood[1:]:
                    if _PHONE_ANCHOR_RE.search(member.text):
                        continue
                    candidate = member.text.strip()
                    if candidate.isdigit():
                        continue
                    if 4 <= len(candidate) <= 60 and not _CONTACT_LABEL_RE.match(candidate):
                        contact = candidate
                        break
            if contact:
                found.setdefault("consumer_care", []).append(
                    Trace(value={"contact": contact}, blocks=hood_blocks, raw_text=contact)
                )

            # The contact block's own tail after its indicator (e.g. a
            # "Tollfree <number>" follower line) carries the value too.
            for member in hood[1:]:
                inner = _CONTACT_CAPTURE_RE.search(member.text)
                if inner:
                    candidate = inner.group(2).strip(" :;,.-—")
                    if candidate and not _CONTACT_LABEL_RE.match(candidate):
                        found.setdefault("consumer_care", []).append(
                            Trace(
                                value={"contact": candidate},
                                blocks=[*line.blocks, *member.blocks],
                                raw_text=member.text.strip(),
                            )
                        )
                        break
        return found

    def _extract_website(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        """Websites are unambiguous anywhere on the label — no spatial
        anchor exists for them, so they are scanned document-wide."""
        traces = []
        for block in blocks:
            url = norm.normalize_website(block.text)
            if url:
                traces.append(Trace(value={"url": url}, blocks=[block], raw_text=block.text.strip()))
        return traces

    def _extract_country(self, lines: list[VisualLine]):
        """Explicit declarations only — "India" inside an address is never
        a country of origin."""
        traces = []
        for line, _match in spatial.find_anchor(
            lines, re.compile("|".join(p.pattern for p in _COUNTRY_RES), re.IGNORECASE)
        ):
            for pattern in _COUNTRY_RES:
                match = pattern.search(line.text)
                if match:
                    traces.append(
                        Trace(
                            value={"country": match.group(1).strip(" .,")},
                            blocks=line.blocks,
                            raw_text=match.group().strip(),
                        )
                    )
                    break
        return traces

    def _extract_ingredients(self, lines: list[VisualLine]) -> list[Trace]:
        """Ingredients from the INGREDIENTS anchor's neighborhood only.

        Wrapped lines are harvested PER BLOCK: only blocks overlapping the
        anchor's column span join the value, so a foreign column sharing the
        visual line (e.g. the product subtitle on a multi-column label) is
        excluded while the ingredient text beside/below the anchor is kept.
        The nutrition table sits ABOVE the anchor and can never be reached.
        Collection stops at the first unrelated declaration.
        """
        traces = []
        for line, match in spatial.find_anchor(lines, _INGREDIENTS_RE):
            collected = [*line.blocks]
            parts: list[str] = []
            anchor_x0 = min((b.bbox or {}).get("x", 0) for b in line.blocks)
            anchor_x1 = max(
                (b.bbox or {}).get("x", 0) + (b.bbox or {}).get("width", 0)
                for b in line.blocks
            )
            rest = line.text[match.end() :].strip(" :—-")
            if rest:
                parts.append(rest)
            # Wrapped lines below: only this anchor's column, until an
            # unrelated declaration starts.
            for follower in spatial.neighborhood(lines, line, below=3)[1:]:
                if _RESERVED_RE.search(follower.text) or "flavour" in follower.text.lower():
                    break
                taken = [
                    b
                    for b in follower.blocks
                    if (b.bbox or {}).get("x", 0) + (b.bbox or {}).get("width", 0)
                    > anchor_x0 + 8
                    and (b.bbox or {}).get("x", 0) < anchor_x1 - 8
                ]
                if taken:
                    parts.extend(b.text.strip() for b in taken)
                    collected.extend(taken)
            if not parts:
                continue
            joined = ""
            for part in parts:
                if not joined:
                    joined = part
                elif joined.endswith((",", ".")) or part.startswith("("):
                    joined += " " + part
                else:
                    joined += ", " + part
            # OCR line-artifacts inside ingredient words ("Edible\ Vegetable",
            # "lodised|Salt") are spacing noise, not content: they become
            # spaces deterministically (§17/§18 — no semantic rewrites).
            joined = re.sub(r"[\\|]", " ", joined)
            joined = re.sub(r"\s+,", ",", joined)
            joined = re.sub(r",{2,}", ",", joined)
            joined = re.sub(r"\s{2,}", " ", joined).strip()
            # §18: single context-gated correction, deterministic and safe.
            for pattern, replacement in _INGREDIENT_FIXES:
                joined = pattern.sub(replacement, joined)
            traces.append(
                Trace(
                    value={"ingredients": joined},
                    blocks=_dedup(collected),
                    raw_text=" ".join(b.text for b in collected),
                )
            )
        return traces

    def _extract_veg(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for block in blocks:
            is_nonveg = re.search(r"\bnon[\s-]?veg(?:etarian)?\b", block.text, re.IGNORECASE)
            is_veg = re.search(r"\bveg(?:etarian)?\b", block.text, re.IGNORECASE)
            if is_nonveg:
                traces.append(
                    Trace(
                        value={"declaration": "non_vegetarian"},
                        blocks=[block],
                        raw_text=is_nonveg.group().strip(),
                    )
                )
            elif is_veg:
                traces.append(
                    Trace(
                        value={"declaration": "vegetarian"},
                        blocks=[block],
                        raw_text=is_veg.group().strip(),
                    )
                )
        return traces

    # -------------------------------------------------- public contract

    def extract_fields(self, pages: list[OCRPageIn]) -> list[ExtractedFieldOut]:
        blocks = [block for page in pages for block in page.blocks]
        lines = spatial.group_lines(blocks)
        # Confidence: strongly-anchored same-line reads carry the configured
        # deterministic confidence; reads joined across blocks (the value
        # below the anchor, wrapped declarations) are context-derived and
        # carry the lower multi-block confidence. Kept separate from OCR
        # confidence by definition; tunable via configuration.
        rule_confidence = get_settings().extraction_confidence
        multi_block_confidence = round(rule_confidence - 5.0, 1)  # context-derived
        traces_by_field: dict[str, list[Trace]] = {
            "mrp": self._extract_mrp(lines),
            "net_quantity": self._extract_net_quantity(lines),
            "product_name": self._extract_product_name(blocks),
            "manufacturer": self._extract_role("manufacturer", lines),
            "packer": self._extract_role("packer", lines),
            "importer": self._extract_role("importer", lines),
            "marketer": self._extract_role("marketer", lines),
            "manufacturer_address": self._extract_role_address("manufacturer", lines),
            "packer_address": self._extract_role_address("packer", lines),
            "importer_address": self._extract_role_address("importer", lines),
            "batch_number": self._extract_code("batch_number", "batch", lines),
            "lot_number": self._extract_code("lot_number", "lot", lines),
            "website": self._extract_website(blocks),
            "country_of_origin": self._extract_country(lines),
            "ingredients": self._extract_ingredients(lines),
            "vegetarian_non_vegetarian": self._extract_veg(blocks),
        }
        traces_by_field.update(self._extract_dates(lines))
        traces_by_field.update(self._extract_contact(lines))

        fields = []
        for name in FIELD_NAMES:
            traces = traces_by_field.get(name, [])
            confidence = (
                multi_block_confidence
                if traces and len(traces[0].blocks) > 1
                else rule_confidence
            )
            fields.append(_field(name, traces, extraction_confidence=confidence))
        return fields
