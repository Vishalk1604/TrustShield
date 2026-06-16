"""PAN-card field extraction (KYC). Handles both label-style text ('Name:', 'PAN:')
and free-form OCR of a real PAN card (the PAN number appears standalone)."""

from __future__ import annotations

import re

from services.forensics.app.ingest.normalize import parse_date

_PAN_RE = re.compile(r"[A-Za-z]{5}[0-9]{4}[A-Za-z]")
_DOB_RE = re.compile(
    r"(?:Date of Birth|DOB|D\.?O\.?B\.?)\s*[:\-]?\s*"
    r"([0-3]?\d[/\-.][0-3A-Za-z]{1,9}[/\-.]\d{2,4})",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\bName\s*[:\-]?\s*([A-Za-z][A-Za-z .]+)")


def extract_pan(text: str) -> dict:
    result: dict = {"doc_type": "pan"}
    m = _PAN_RE.search(text)
    if m:
        result["pan"] = m.group(0).upper()
    nm = _NAME_RE.search(text)
    if nm:
        result["name"] = nm.group(1).strip()
    dm = _DOB_RE.search(text)
    if dm:
        result["dob"] = parse_date(dm.group(1)) or dm.group(1)
    return result
