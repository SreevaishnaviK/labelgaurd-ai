"""Reusable normalization helpers for extracted values.

Normalizers convert OCR text into structured values without destroying the
source: raw_text is always preserved by the caller alongside the normalized
value.
"""
import re

# --- currency ---

_CURRENCY_TOKENS = {"₹", "rs", "rs.", "inr"}


def normalize_currency(token: str) -> str | None:
    """Map a currency token (₹, Rs, Rs., INR) to INR, or None if unknown."""
    return "INR" if token.strip().lower() in _CURRENCY_TOKENS else None


# --- net quantity units ---

_UNIT_MAP = {
    "mg": "mg",
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "ml": "ml",
    "l": "L",
    "ltr": "L",
    "litre": "L",
    "litres": "L",
    "liter": "L",
    "liters": "L",
}


def normalize_unit(token: str) -> str | None:
    """Map a unit spelling to its canonical form (g, kg, mg, ml, L)."""
    return _UNIT_MAP.get(token.strip().lower().rstrip("."))


def normalize_mass(value: float, unit: str) -> tuple[float, str] | None:
    """Convert a mass to its canonical unit (kg for >=1 kg values, else g)."""
    canonical = normalize_unit(unit)
    if canonical not in ("g", "kg", "mg"):
        return None
    factors = {"mg": 0.001, "g": 1.0, "kg": 1000.0}
    grams = value * factors[canonical]
    if grams >= 1000:
        return (round(grams / 1000, 3), "kg")
    return (round(grams, 3), "g")


def normalize_volume(value: float, unit: str) -> tuple[float, str] | None:
    """Convert a volume to its canonical unit (L for >=1 L values, else ml)."""
    canonical = normalize_unit(unit)
    if canonical not in ("ml", "L"):
        return None
    ml = value * (1000.0 if canonical == "L" else 1.0)
    if ml >= 1000:
        return (round(ml / 1000, 3), "L")
    return (round(ml, 3), "ml")


# --- phones / emails / urls ---

_PHONE_RE = re.compile(r"(?:\+91[\s-]?)?(?:\d[\s-]?){10,12}\d")


def normalize_phone(text: str) -> str | None:
    """Extract a phone number, normalizing digits but keeping the leading +91."""
    match = _PHONE_RE.search(text)
    if not match:
        return None
    raw = match.group()
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 12:
        return None
    if raw.lstrip().startswith("+"):
        return f"+{digits}"
    return digits


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def normalize_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group().lower() if match else None


_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?:/[^\s,;]*)?",
    re.IGNORECASE,
)


def normalize_website(text: str) -> str | None:
    """Extract a website. The TLD must be alphabetic so amounts like 68.00
    are never mistaken for domains."""
    match = _URL_RE.search(text)
    if not match:
        return None
    url = match.group().rstrip(".,;")
    host = url.lower().removeprefix("https://").removeprefix("http://").split("/", 1)[0]
    tld = host.rsplit(".", 1)[-1]
    if not tld.isalpha():
        return None
    return url if url.lower().startswith("http") else f"https://{url}"
