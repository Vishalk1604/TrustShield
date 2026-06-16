"""Aadhaar-card field extraction (KYC). Captures the (possibly masked) 12-digit number,
gender, DOB/YOB and name from a real Aadhaar card's OCR text. Per the project's privacy
posture only MASKED Aadhaar should be used in practice (first 8 digits hidden)."""

from __future__ import annotations

import re

from services.forensics.app.ingest.normalize import parse_date

# 4-4-4 grouping; middle groups may be masked (X/*). Anchored on the trailing 4 real digits.
_AADHAAR_RE = re.compile(r"\b([0-9X*]{4}\s?[0-9X*]{4}\s?\d{4})\b", re.IGNORECASE)
_GENDER_RE = re.compile(r"\b(MALE|FEMALE|TRANSGENDER)\b", re.IGNORECASE)
_DOB_RE = re.compile(
    r"(?:DOB|Date of Birth)\s*[:\-]?\s*([0-3]?\d[/\-.][0-3]?\d[/\-.]\d{2,4})", re.IGNORECASE
)
_YOB_RE = re.compile(r"(?:YOB|Year of Birth)\s*[:\-]?\s*(\d{4})", re.IGNORECASE)
_NAME_RE = re.compile(r"\bName\s*[:\-]?\s*([A-Za-z][A-Za-z .]+)")


def extract_aadhaar(text: str) -> dict:
    result: dict = {"doc_type": "aadhaar"}
    m = _AADHAAR_RE.search(text)
    if m:
        result["aadhaar"] = re.sub(r"\s+", "", m.group(1)).upper()
    g = _GENDER_RE.search(text)
    if g:
        result["gender"] = g.group(1).upper()
    dm = _DOB_RE.search(text)
    if dm:
        result["dob"] = parse_date(dm.group(1)) or dm.group(1)
    else:
        ym = _YOB_RE.search(text)
        if ym:
            result["dob"] = ym.group(1)
    nm = _NAME_RE.search(text)
    if nm:
        result["name"] = nm.group(1).strip()
    return result
