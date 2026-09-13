"""Deterministic field extraction from OCR blocks.

Rule-based, no network, no LLM. Every candidate trace must reference real OCR
block IDs; nothing is invented. Ambiguity is reported, never silently resolved.
"""
import re
from dataclasses import dataclass, field

from app.config import get_settings
from app.extraction import normalization as norm
from app.extraction.base import BaseFieldExtractor
from app.schemas.extraction import (
    EvidenceRef,
    ExtractedFieldOut,
    FieldCandidate,
    OCRBlockIn,
    OCRPageIn,
)
from app.utils.text import sort_blocks

# ---------------------------------------------------------------- patterns

_MONEY = r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
_MRP_RE = re.compile(rf"\b(?:m\.?r\.?p|maximum\s+retail\s+price)\b\.?[:\s]*{_MONEY}", re.IGNORECASE)

_NET_RE = re.compile(
    r"\b(?:net\s+(?:qty|quantity|wt|weight)|contents)[.:]?\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*(mg|g|gm|gms|kgs?|ml|l|ltr|litres?|liters?)\b\.?",
    re.IGNORECASE,
)

_DATE = r"([0-9]{1,2}[\/\-.][0-9]{1,2}[\/\-.][0-9]{2,4}|[0-9]{1,2}[\/\-.][0-9]{2,4}|[0-9]{2,4}[\/\-.][0-9]{2,4})"
_DATE_FIELDS = [
    ("manufacturing_date", r"\b(?:mfd|mfg|manufactured(?:\s+on)?|manufacturing\s+date|mfg\.?date)\b[:.\s]*"),
    ("packing_date", r"\b(?:pkd|packed(?:\s+on)?|packing\s+date)\b[:.\s]*"),
    ("best_before", r"\bbest\s+before\b[:.\s]*"),
    ("use_by", r"\buse\s+by\b[:.\s]*"),
    ("expiry_date", r"\b(?:exp|expiry(?:\s+date)?)\b[:.\s]*"),
]

_PHONE_INDICATORS = r"(?:consumer\s+care|consumer\s+complaints|customer\s+care|customer\s+service|toll\s*free|helpline|contact\s+us)"
_PHONE_RE = re.compile(rf"{_PHONE_INDICATORS}[^0-9+]*(\+?91[\s-]?[0-9][0-9\s-]{{8,11}}|[0-9]{{10,12}})", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_WEBSITE_RE = re.compile(r"\b(?:https?://|www\.)[^\s,;]+|\b[a-z0-9-]+\.(?:com|in|org|net|co\.in)\b(?:/[^\s,;]*)?", re.IGNORECASE)

_ROLES = {
    "manufacturer": r"\bmanufactured\s*(?:&|and)\s*(?:packed|marketed)?\s*by\b|\bmanufactured\s+by\b|\bmfd\s+by\b",
    "packer": r"\b(?:manufactured\s*(?:&|and)\s*packed|packed\s*(?:&|and)\s*marketed|packed)\s+by\b",
    "importer": r"\b(?:imported\s+by|importer)\b[:\s]*",
}
_ROLE_RES = {role: re.compile(pattern, re.IGNORECASE) for role, pattern in _ROLES.items()}

_BATCH_NO_RE = re.compile(
    r"\bbatch\s*(?:no|number)?\b\s*[:.#\-]?\s*([A-Za-z0-9][A-Za-z0-9/\-_.]{2,30})",
    re.IGNORECASE,
)
_LOT_NO_RE = re.compile(
    r"\blot\s*(?:no|number)?\b\s*[:.#\-]?\s*([A-Za-z0-9][A-Za-z0-9/\-_.]{2,30})",
    re.IGNORECASE,
)

# A line that looks like an address rather than a company name: digits
# (plot/house/PIN numbers), commas, or common Indian address words.
_ADDRESS_LINE_RE = re.compile(
    r"\d|,|\b(?:plot|street|road|nagar|colony|sector|industrial|estate|layout|"
    r"floor|building|avenue|marg|highway|village|taluk|district|pin)\b",
    re.IGNORECASE,
)
_COUNTRY_RES = [
    re.compile(r"\bcountry\s+of\s+origin\b[:\s]*([A-Za-z][A-Za-z\s]{2,40})", re.IGNORECASE),
    re.compile(r"\bmade\s+in\s+([A-Za-z][A-Za-z\s]{2,40})", re.IGNORECASE),
    re.compile(r"\bproduct\s+of\s+([A-Za-z][A-Za-z\s]{2,40})", re.IGNORECASE),
]
_INGREDIENTS_RE = re.compile(r"\bingredients?\b[:\-]?\s*(.+)", re.IGNORECASE | re.DOTALL)
_VEG_RE = re.compile(r"\bnon[\s-]?veg(?:etarian)?\b|\bveg(?:etarian)?\b", re.IGNORECASE)

# Blocks that must never be picked as the product name.
_RESERVED_RE = re.compile(
    r"\b(?:mrp|m\.r\.p|maximum\s+retail|net\s+(?:qty|quantity|wt|weight)|contents|"
    r"manufactured|packed|marketed|imported|importer|batch|lot\s*no|mfd|mfg|pkd|"
    r"best\s+before|use\s+by|exp|expiry|consumer\s+care|customer\s+care|helpline|"
    r"toll\s*free|ingredients|country\s+of\s+origin|made\s+in|www\.|@)",
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
                FieldCandidate(raw_text=t.raw_text or " ".join(b.text for b in t.blocks), value=t.value)
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


class DeterministicFieldExtractor(BaseFieldExtractor):
    """Rule-based extractor: indicator keywords + normalization + evidence."""

    name = "deterministic"

    # -------------------------------------------------- per-field extractors

    def _extract_mrp(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for block in blocks:
            match = _MRP_RE.search(block.text)
            if match:
                amount = float(match.group(1).replace(",", ""))
                traces.append(
                    Trace(
                        value={"amount": amount, "currency": "INR"},
                        blocks=[block],
                        raw_text=match.group().strip(),
                    )
                )
        return traces

    def _extract_net_quantity(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for block in blocks:
            match = _NET_RE.search(block.text)
            if match:
                value, unit = float(match.group(1)), match.group(2)
                normalized = norm.normalize_mass(value, unit) or norm.normalize_volume(value, unit)
                if normalized:
                    traces.append(
                        Trace(
                            value={"value": normalized[0], "unit": normalized[1]},
                            blocks=[block],
                            raw_text=match.group().strip(),
                        )
                    )
        return traces

    def _extract_product_name(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        """Prominence heuristic: largest area among the top-reading-order
        blocks that are not reserved (MRP, net qty, roles, dates, ...) and
        are predominantly alphabetic (rejects phone numbers and codes)."""
        ordered = sort_blocks(blocks)
        eligible = [
            b
            for b in ordered
            if not _RESERVED_RE.search(b.text)
            and sum(ch.isalpha() for ch in b.text) >= 0.6 * max(len(b.text.strip()), 1)
        ]
        # Restrict to the top third of reading order — a product name sits high.
        if eligible:
            top_y = min((b.bbox.get("y", 0) for b in eligible), default=0)
            height = max((b.bbox.get("y", 0) + b.bbox.get("height", 0) for b in eligible), default=1)
            band = top_y + (height - top_y) * 0.5
            eligible = [b for b in eligible if b.bbox.get("y", 0) <= band]
        if not eligible:
            return []
        best = max(eligible, key=lambda b: (b.bbox or {}).get("width", 0) * (b.bbox or {}).get("height", 0))
        words = best.text.strip()
        if not words or len(words) < 3:
            return []
        return [Trace(value={"name": words}, blocks=[best], raw_text=best.text.strip())]

    def _role_declarations(self, role: str, blocks: list[OCRBlockIn]) -> list[dict]:
        """Parse each role declaration into name vs address lines.

        OCR may split a declaration across lines and blocks. The first plain
        line after the indicator is the company name; lines that look like an
        address (digits, commas, place words) belong to the address. Scanning
        stops at any other field indicator so nothing is double-counted.
        """
        ordered = sort_blocks(blocks)
        declarations = []
        for index, block in enumerate(ordered):
            match = _ROLE_RES[role].search(block.text)
            if not match:
                continue
            lines: list[tuple[str, OCRBlockIn]] = [
                (line.strip(" :-—"), block) for line in block.text[match.end():].splitlines()
            ]
            bbox = block.bbox or {}
            prev_bbox = bbox
            for follower in ordered[index + 1 : index + 4]:
                follower_bbox = follower.bbox or {}
                # Per-line pitch check: a gap larger than ~2.5 line heights
                # from the PREVIOUS line ends the declaration (blank space).
                prev_h = max(prev_bbox.get("height", 40), follower_bbox.get("height", 40))
                if abs(follower_bbox.get("y", 0) - prev_bbox.get("y", 0)) > prev_h * 2.5:
                    break
                if _ROLE_RES[role].search(follower.text) or _RESERVED_RE.search(follower.text):
                    break
                lines.extend((line.strip(" :-—"), follower) for line in follower.text.splitlines())
                prev_bbox = follower_bbox

            name: list[str] = []
            address: list[str] = []
            name_blocks: list[OCRBlockIn] = []
            address_blocks: list[OCRBlockIn] = []
            for line, source in lines:
                if not line:
                    continue
                if _ROLE_RES[role].search(line) or _RESERVED_RE.search(line):
                    break
                if _looks_like_address_line(line):
                    address.append(line)
                    if source not in address_blocks:
                        address_blocks.append(source)
                elif not name and not address:
                    name.append(line)
                    if source not in name_blocks:
                        name_blocks.append(source)
                else:
                    break  # second plain line after the name: outside declaration
            declarations.append(
                {
                    "name": " ".join(name).strip(" ,.-") or None,
                    "name_blocks": _dedup([block, *name_blocks]),
                    "address": address or None,
                    "address_blocks": _dedup(address_blocks),
                    # The name's evidence spans the whole declaration
                    # (spec: multi-block evidence for the company).
                    "all_blocks": _dedup([block, *name_blocks, *address_blocks]),
                }
            )
        return declarations

    def _extract_role(self, role: str, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for declaration in self._role_declarations(role, blocks):
            if declaration["name"]:
                traces.append(
                    Trace(
                        value={"name": declaration["name"]},
                        blocks=declaration["all_blocks"],
                        raw_text=declaration["name"],
                    )
                )
        return traces

    def _extract_role_address(self, role: str, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for declaration in self._role_declarations(role, blocks):
            if declaration["address"]:
                joined = ", ".join(declaration["address"])
                traces.append(
                    Trace(
                        value={"address": joined},
                        blocks=declaration["address_blocks"],
                        raw_text=" ".join(declaration["address"]),
                    )
                )
        return traces

    def _extract_dates(self, blocks: list[OCRBlockIn]) -> dict[str, list[Trace]]:
        found: dict[str, list[Trace]] = {}
        ordered = sort_blocks(blocks)
        for index, block in enumerate(ordered):
            for field_name, indicator in _DATE_FIELDS:
                match = re.search(indicator + _DATE, block.text, re.IGNORECASE)
                if match:
                    found.setdefault(field_name, []).append(
                        Trace(
                            value={"date": match.group(1).strip()},
                            blocks=[block],
                            raw_text=match.group().strip(),
                        )
                    )
                    continue
                # Indicator alone on its line: the date often sits in the next
                # reading-order block — keep both as evidence.
                if re.search(indicator, block.text, re.IGNORECASE) and index + 1 < len(ordered):
                    follower = ordered[index + 1]
                    date_match = re.fullmatch(_DATE + r"\.?", follower.text.strip(), re.IGNORECASE)
                    if date_match:
                        found.setdefault(field_name, []).append(
                            Trace(
                                value={"date": date_match.group(1).strip()},
                                blocks=[block, follower],
                                raw_text=f"{block.text.strip()} {follower.text.strip()}",
                            )
                        )
        return found

    @staticmethod
    def _extract_code(pattern: re.Pattern, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for block in blocks:
            for match in pattern.finditer(block.text):
                traces.append(
                    Trace(
                        value={"batch": match.group(1).strip()},
                        blocks=[block],
                        raw_text=match.group().strip(),
                    )
                )
        return traces

    def _extract_contact(self, blocks: list[OCRBlockIn]) -> dict[str, list[Trace]]:
        found: dict[str, list[Trace]] = {}
        for block in blocks:
            has_indicator = bool(re.search(_PHONE_INDICATORS, block.text, re.IGNORECASE))
            if has_indicator:
                phone = norm.normalize_phone(block.text)
                if phone:
                    found.setdefault("customer_care_phone", []).append(
                        Trace(value={"phone": phone}, blocks=[block], raw_text=block.text.strip())
                    )
                email = norm.normalize_email(block.text)
                if email:
                    found.setdefault("customer_care_email", []).append(
                        Trace(value={"email": email}, blocks=[block], raw_text=block.text.strip())
                    )
            website = norm.normalize_website(block.text)
            if website:
                found.setdefault("website", []).append(
                    Trace(value={"url": website}, blocks=[block], raw_text=block.text.strip())
                )
        return found

    def _extract_consumer_care(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for block in blocks:
            match = re.search(rf"({_PHONE_INDICATORS})[:\s]*([^\n]{{4,60}})", block.text, re.IGNORECASE)
            if match:
                traces.append(
                    Trace(
                        value={"contact": match.group(2).strip(" :-")},
                        blocks=[block],
                        raw_text=match.group().strip(),
                    )
                )
        return traces

    def _extract_country(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        for block in blocks:
            for pattern in _COUNTRY_RES:
                match = pattern.search(block.text)
                if match:
                    traces.append(
                        Trace(
                            value={"country": match.group(1).strip(" .,")},
                            blocks=[block],
                            raw_text=match.group().strip(),
                        )
                    )
                    break
        return traces

    def _extract_ingredients(self, blocks: list[OCRBlockIn]) -> list[Trace]:
        traces = []
        ordered = sort_blocks(blocks)
        for index, block in enumerate(ordered):
            match = _INGREDIENTS_RE.search(block.text)
            if not match:
                continue
            text = match.group(1).strip()
            collected = [block]
            # Ingredients lists commonly wrap across following lines.
            if len(text) < 40:
                for follower in ordered[index + 1 : index + 4]:
                    if _RESERVED_RE.search(follower.text):
                        break
                    text += " " + follower.text.strip()
                    collected.append(follower)
            traces.append(
                Trace(
                    value={"ingredients": text.strip()},
                    blocks=collected,
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
                traces.append(Trace(value={"declaration": "non_vegetarian"}, blocks=[block], raw_text=is_nonveg.group().strip()))
            elif is_veg:
                traces.append(Trace(value={"declaration": "vegetarian"}, blocks=[block], raw_text=is_veg.group().strip()))
        return traces

    # -------------------------------------------------- public contract

    def extract_fields(self, pages: list[OCRPageIn]) -> list[ExtractedFieldOut]:
        blocks = [block for page in pages for block in page.blocks]
        # Extraction confidence: deterministic rule gates passed. Kept separate
        # from OCR confidence by definition; tunable via configuration.
        rule_confidence = get_settings().extraction_confidence
        multi_block_confidence = round(rule_confidence - 5.0, 1)  # context-derived
        traces_by_field: dict[str, list[Trace]] = {
            "mrp": self._extract_mrp(blocks),
            "net_quantity": self._extract_net_quantity(blocks),
            "product_name": self._extract_product_name(blocks),
            "manufacturer": self._extract_role("manufacturer", blocks),
            "packer": self._extract_role("packer", blocks),
            "importer": self._extract_role("importer", blocks),
            "manufacturer_address": self._extract_role_address("manufacturer", blocks),
            "packer_address": self._extract_role_address("packer", blocks),
            "importer_address": self._extract_role_address("importer", blocks),
            "batch_number": self._extract_code(_BATCH_NO_RE, blocks),
            "lot_number": self._extract_code(_LOT_NO_RE, blocks),
            "country_of_origin": self._extract_country(blocks),
            "ingredients": self._extract_ingredients(blocks),
            "vegetarian_non_vegetarian": self._extract_veg(blocks),
            "consumer_care": self._extract_consumer_care(blocks),
        }
        traces_by_field.update(self._extract_dates(blocks))
        traces_by_field.update(self._extract_contact(blocks))

        field_order = [
            "product_name", "manufacturer", "packer", "importer",
            "manufacturer_address", "packer_address", "importer_address",
            "net_quantity", "mrp", "manufacturing_date", "packing_date",
            "best_before", "use_by", "expiry_date", "consumer_care",
            "customer_care_phone", "customer_care_email", "website",
            "batch_number", "lot_number", "country_of_origin", "ingredients",
            "vegetarian_non_vegetarian",
        ]
        fields = []
        for name in field_order:
            traces = traces_by_field.get(name, [])
            confidence = (
                multi_block_confidence
                if traces and len(traces[0].blocks) > 1
                else rule_confidence
            )
            fields.append(_field(name, traces, extraction_confidence=confidence))
        return fields
