"""Indian-document normalization + identifier validators (plan.md §7, KYC).

Pure-Python, dependency-free, fully unit-testable. Used by the extractors to parse
real-document values and by the KYC layer to validate identifiers.

- `parse_amount`  : "Rs. 1,45,000" / "₹12,34,567" / "5 lakh" / "1.2 crore" -> float
- `parse_date`    : DD/MM/YYYY, DD-MMM-YYYY, etc. -> ISO "YYYY-MM-DD"
- `validate_pan`  : structure + holder-type (no public checksum exists for PAN)
- `validate_aadhaar` : Verhoeff checksum for full 12 digits; format-only for masked
- `validate_ifsc` : 11-char bank/branch code structure
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

# --------------------------------------------------------------------------
# Money / date parsing
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def parse_amount(s: Optional[str]) -> Optional[float]:
    """Parse an Indian currency string to a float. Handles lakh/crore words and
    Indian comma grouping. Returns None if no number is present."""
    if s is None:
        return None
    text = str(s)
    low = text.lower()
    mult = 1.0
    if re.search(r"\bcrores?\b", low):
        mult = 1e7
    elif re.search(r"\bla(?:kh|c)s?\b", low):
        mult = 1e5
    cleaned = text.replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("INR", "")
    m = _NUM_RE.search(cleaned)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "")) * mult
    except ValueError:
        return None


_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
    "%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%d/%m/%y",
)


def parse_date(s: Optional[str]) -> Optional[str]:
    """Parse a date in common Indian formats to ISO 'YYYY-MM-DD'. None on failure."""
    if not s:
        return None
    text = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    # Fall back to a date-like substring (e.g. embedded in a sentence).
    m = re.search(r"\d{1,2}[/-][A-Za-z0-9]{1,9}[/-]\d{2,4}", text)
    if m and m.group(0) != text:
        return parse_date(m.group(0))
    return None


# --------------------------------------------------------------------------
# Verhoeff checksum (used by Aadhaar)
# --------------------------------------------------------------------------

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 9, 1, 6, 3, 7, 2, 4),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_validate(number: str) -> bool:
    """True if `number` (digits incl. its trailing check digit) passes the Verhoeff check."""
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_generate(number: str) -> int:
    """Compute the Verhoeff check digit for `number` (without a check digit)."""
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return _VERHOEFF_INV[c]


# --------------------------------------------------------------------------
# Identifier validators
# --------------------------------------------------------------------------

_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_PAN_HOLDER = {
    "P": "Individual", "C": "Company", "H": "HUF (Hindu Undivided Family)",
    "F": "Firm/LLP", "A": "Association of Persons", "T": "Trust",
    "B": "Body of Individuals", "L": "Local Authority",
    "J": "Artificial Juridical Person", "G": "Government",
}


def validate_pan(pan: Optional[str]) -> dict:
    """Validate PAN structure (AAAAA9999A) + decode the holder-type char.

    PAN has no public checksum, so this is a structural check: 5 letters, 4 digits,
    1 letter, with the 4th char a recognised holder-type code.
    """
    if not pan:
        return {"valid": False, "normalized": None, "reason": "empty"}
    norm = re.sub(r"\s+", "", pan).upper()
    if not _PAN_RE.match(norm):
        return {"valid": False, "normalized": norm, "reason": "bad format (expect AAAAA9999A)"}
    holder = _PAN_HOLDER.get(norm[3])
    if holder is None:
        return {"valid": False, "normalized": norm, "reason": f"invalid holder-type char '{norm[3]}'"}
    return {"valid": True, "normalized": norm, "holder_type": holder, "reason": "ok"}


def validate_aadhaar(aadhaar: Optional[str]) -> dict:
    """Validate an Aadhaar number.

    Full 12 digits -> Verhoeff checksum. Masked (e.g. 'XXXXXXXX1234' / '**** **** 1234')
    -> format-only (checksum cannot be verified without all digits). Per the project's
    privacy posture, only masked Aadhaar should be handled in practice.
    """
    if not aadhaar:
        return {"valid": False, "masked": False, "checksum_verified": False, "reason": "empty"}
    raw = re.sub(r"[\s-]", "", str(aadhaar))
    masked = bool(re.search(r"[X*x]", raw))
    if masked:
        # Expect 12 chars, last 4 digits, the rest masked.
        if re.match(r"^[X*x]{8}\d{4}$", raw):
            return {"valid": True, "masked": True, "checksum_verified": False,
                    "reason": "masked — format ok, checksum not verifiable"}
        if len(raw) == 12 and raw[-4:].isdigit():
            return {"valid": True, "masked": True, "checksum_verified": False,
                    "reason": "partially masked — last 4 digits present"}
        return {"valid": False, "masked": True, "checksum_verified": False,
                "reason": "bad masked format (expect 8 masked + last 4 digits)"}
    if not (raw.isdigit() and len(raw) == 12):
        return {"valid": False, "masked": False, "checksum_verified": False,
                "reason": "bad format (expect 12 digits)"}
    if raw[0] in "01":
        return {"valid": False, "masked": False, "checksum_verified": True,
                "reason": "Aadhaar cannot start with 0 or 1"}
    ok = verhoeff_validate(raw)
    return {"valid": ok, "masked": False, "checksum_verified": True,
            "reason": "ok" if ok else "Verhoeff checksum failed"}


_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def validate_ifsc(ifsc: Optional[str]) -> dict:
    """Validate IFSC structure: 4-letter bank code + '0' + 6-char branch code."""
    if not ifsc:
        return {"valid": False, "normalized": None, "reason": "empty"}
    norm = re.sub(r"\s+", "", ifsc).upper()
    if not _IFSC_RE.match(norm):
        return {"valid": False, "normalized": norm, "reason": "bad format (expect AAAA0XXXXXX)"}
    return {"valid": True, "normalized": norm, "bank_code": norm[:4], "reason": "ok"}
