"""Entity extraction from loan-document PDFs — Phase 2.

Fast path: uses PyMuPDF's embedded text layer (all synthetic PDFs have text).
Fallback: Tesseract OCR for image-only scans (production path).

Each doc_type has its own extractor that applies regex patterns matching the
pdf_builder.py layouts. Returns a plain dict of extracted fields; None means
the field was not found.

Local-only: no network, no external service calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF

from services.forensics.app.ocr import ocr_pdf

# --------------------------------------------------------------------------
# Text extraction helpers
# --------------------------------------------------------------------------

def _embedded_text(path: str) -> str:
    """Extract embedded text from all pages, preserving line breaks."""
    with fitz.open(path) as doc:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def _has_embedded_text(path: str) -> bool:
    """Return True if the PDF has meaningful embedded text (not just spaces/noise)."""
    with fitz.open(path) as doc:
        for page in doc:
            if len(page.get_text("text").strip()) > 10:
                return True
    return False


def _doc_text(path: str) -> str:
    """Get text from PDF: embedded first, OCR if the page appears image-only."""
    if _has_embedded_text(path):
        return _embedded_text(path)
    return ocr_pdf(path)


# --------------------------------------------------------------------------
# Money parsing
# --------------------------------------------------------------------------

def _parse_money(s: str) -> Optional[float]:
    """Parse 'Rs. 1,820,000' or '1,820,000' -> 1820000.0. Returns None on failure."""
    cleaned = re.sub(r"Rs\.", "", s).replace(",", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _find_money(pattern: str, text: str) -> Optional[float]:
    """Find a money amount matching `pattern` in `text`. Pattern must include a capture group."""
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        return _parse_money(m.group(1))
    return None


# --------------------------------------------------------------------------
# Per-doc-type extractors
# --------------------------------------------------------------------------

def _extract_identity(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "identity"}
    m = re.search(r"Name:\s+(.+)", text)
    if m:
        result["name"] = m.group(1).strip()
    m = re.search(r"PAN:\s+([A-Z]{5}\d{4}[A-Z])", text)
    if m:
        result["pan"] = m.group(1)
    m = re.search(r"Date of Birth:\s+(\S+)", text)
    if m:
        result["dob"] = m.group(1).strip()
    return result


def _extract_form16(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "form16"}
    # Name: old flat layout ("Employee: X") OR realistic TRACES block ("Name and address of the Employee\nX").
    m = re.search(r"Employee:\s+(.+)", text) or re.search(r"Name and address of the Employee\s*\n\s*(.+)", text)
    if m:
        result["name"] = m.group(1).strip()
    # PAN: old "PAN: X"; realistic shows the deductor PAN then the EMPLOYEE PAN (last one) in the Part A row.
    m = re.search(r"PAN:\s+([A-Z]{5}\d{4}[A-Z])", text)
    if m:
        result["pan"] = m.group(1)
    else:
        pans = re.findall(r"[A-Z]{5}\d{4}[A-Z]", text)
        if pans:
            result["pan"] = pans[-1]            # employee PAN follows the deductor PAN in Part A
    # Employer: old "Employer: X" OR realistic "Name and address of the Employer\nX".
    m = re.search(r"Employer:\s+(.+)", text) or re.search(r"Name and address of the Employer\s*\n\s*(.+)", text)
    if m:
        result["employer"] = m.group(1).strip()
    # Gross income: label and amount may be on same line or adjacent lines
    v = _find_money(r"Gross Salary[^\n]*(?:\n[^\n]*)?\bRs\.\s*([\d,]+)", text)
    if v is None:
        v = _find_money(r"Gross Salary.*?Rs\.\s*([\d,]+)", text)
    result["gross_income"] = v
    # TDS / tax paid
    v = _find_money(r"Tax Deducted[^\n]*(?:\n[^\n]*)?\bRs\.\s*([\d,]+)", text)
    if v is None:
        v = _find_money(r"Tax Deducted.*?Rs\.\s*([\d,]+)", text)
    result["tax_paid"] = v
    # FY
    m = re.search(r"FY\s+(\d{4}-\d{2})", text)
    if m:
        result["fy"] = m.group(1)
    return result


def _extract_salary_slip(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "salary_slip"}
    m = re.search(r"Employee:\s+(.+)", text) or re.search(r"Employee Name:\s+(.+)", text)
    if m:
        result["name"] = m.group(1).strip()
    # Net monthly pay — label and value on same or adjacent lines (old + realistic "Net Pay (take-home)")
    v = _find_money(r"Net Pay[^\n]*(?:\n[^\n]*)?\bRs\.\s*([\d,]+)", text)
    if v is None:
        v = _find_money(r"Net Pay.*?Rs\.\s*([\d,]+)", text)
    result["net_monthly"] = v
    # Employer: old "SALARY SLIP\nEMPLOYER | MONTH" OR realistic header band (line above "Payslip for the month")
    m = re.search(r"SALARY SLIP\s*\n(.+?)\s*\|", text) or re.search(r"(.+?)\n[^\n]*\nPayslip for the month", text)
    if m:
        result["employer"] = m.group(1).strip()
    return result


def _extract_bank_statement(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "bank_statement"}
    # Account holder from header
    m = re.search(r"Holder:\s+(.+)", text)
    if m:
        result["name"] = m.group(1).strip()
    # Account number (masked) from header
    m = re.search(r"Account:\s+(\S+)", text)
    if m:
        result["masked_account"] = m.group(1)
    # All salary-credit amounts. Old flat layout had "SALARY CREDIT … Rs. X" on one line; the realistic
    # statement is a table, so the Credit amount is the first Rs. value on the line(s) AFTER the narration.
    credits = re.findall(r"SALARY CREDIT[^\n]*Rs\.\s*([\d,]+)", text, re.IGNORECASE)
    if not credits:
        credits = re.findall(r"SALARY CREDIT[^\n]*\n\s*Rs\.\s*([\d,]+)", text, re.IGNORECASE)
    parsed = [_parse_money(c) for c in credits if _parse_money(c) is not None]
    result["salary_credits"] = parsed
    if parsed:
        result["monthly_credit"] = parsed[0]  # assume all months same (in clean packets)
        result["implied_annual"] = sum(parsed) / len(parsed) * 12
    return result


def _extract_sale_deed(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "sale_deed"}
    m = re.search(r"Property No:\s+(\S+)", text)
    if m:
        result["property_id"] = m.group(1).strip()
    m = re.search(r"Property Addr:\s+(.+)", text)
    if m:
        result["property_address"] = m.group(1).strip()
    # Owner — could be "Owner (Vendee):" form
    m = re.search(r"Owner\s*\(Vendee\):\s+(.+)", text)
    if m:
        result["owner_name"] = m.group(1).strip()
    m = re.search(r"PAN of Vendee:\s+([A-Z]{5}\d{4}[A-Z])", text)
    if m:
        result["pan"] = m.group(1)
    v = _find_money(r"Consideration:\s*Rs\.\s*([\d,]+)", text)
    result["consideration"] = v
    return result


def _extract_encumbrance_certificate(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "encumbrance_certificate"}
    # Property ID from header subtitle: "Property: SY-217/3B  |  Period: ..."
    m = re.search(r"Property:\s+(\S+)", text)
    if m:
        result["property_id"] = m.group(1).strip()
    m = re.search(r"Owner:\s+(.+)", text)
    if m:
        result["owner_name"] = m.group(1).strip()
    m = re.search(r"Property Addr:\s+(.+)", text)
    if m:
        result["property_address"] = m.group(1).strip()
    # Period
    m = re.search(r"Period:\s+(\S+)", text)
    if m:
        result["period"] = m.group(1).strip()
    # Charges
    result["claims_nil"] = bool(re.search(r"NIL ENCUMBRANCES", text, re.IGNORECASE))
    charge_matches = re.findall(
        r"mortgage in favour of ([^,\n]+),\s*Rs\.\s*([\d,]+),\s*registered\s+(\S+)",
        text, re.IGNORECASE,
    )
    result["charges"] = [
        {"lender": m[0].strip(), "amount": _parse_money(m[1]), "registered_on": m[2]}
        for m in charge_matches
    ]
    return result


def _extract_property_valuation(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "property_valuation"}
    m = re.search(r"Property No:\s+(\S+)", text)
    if m:
        result["property_id"] = m.group(1).strip()
    m = re.search(r"Property Addr:\s+(.+)", text)
    if m:
        result["property_address"] = m.group(1).strip()
    m = re.search(r"Owner:\s+(.+)", text)
    if m:
        result["owner_name"] = m.group(1).strip()
    v = _find_money(r"Assessed Market Value[^\n]*(?:\n[^\n]*)?\bRs\.\s*([\d,]+)", text)
    if v is None:
        v = _find_money(r"Assessed Market Value.*?Rs\.\s*([\d,]+)", text)
    result["valuation_amount"] = v
    return result


def _extract_legal_opinion(text: str) -> dict:
    result: dict[str, Any] = {"doc_type": "legal_opinion"}
    m = re.search(r"Property No:\s+(\S+)", text)
    if m:
        result["property_id"] = m.group(1).strip()
    m = re.search(r"Owner examined:\s+(.+)", text)
    if m:
        result["owner_name"] = m.group(1).strip()
    m = re.search(r"Advocate:\s+(.+)", text)
    if m:
        result["advocate"] = m.group(1).strip()
    result["title_clear"] = bool(re.search(r"title is clear", text, re.IGNORECASE))
    result["title_unclear"] = bool(re.search(r"title is NOT clear", text, re.IGNORECASE))
    return result


def _extract_address_proof(text: str) -> dict:
    """Light extraction for a proof-of-address doc (utility bill / passport / voter / DL).

    Real address proofs vary wildly, so this is intentionally forgiving: capture a holder
    name, an address block, and an issue/bill date when present. Used for KYC POA presence
    + name-consistency, not for any monetary check.
    """
    result: dict[str, Any] = {"doc_type": "address_proof"}
    m = re.search(
        r"(?:Consumer Name|Customer Name|Name of Consumer|Holder|Name)\s*[:\-]?\s*([A-Za-z][A-Za-z .]{2,})",
        text, re.IGNORECASE,
    )
    if m:
        result["name"] = m.group(1).strip()
    m = re.search(
        r"(?:Service Address|Billing Address|Permanent Address|Address)\s*[:\-]?\s*(.+)",
        text, re.IGNORECASE,
    )
    if m:
        result["address"] = m.group(1).strip()[:200]
    m = re.search(
        r"(?:Bill Date|Date of Issue|Issue Date|Date)\s*[:\-]?\s*"
        r"([0-3]?\d[/\-.][0-3A-Za-z]{1,9}[/\-.]\d{2,4})",
        text, re.IGNORECASE,
    )
    if m:
        result["issue_date"] = m.group(1).strip()
    return result


def _extract_generic(text: str) -> dict:
    return {"doc_type": "other"}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_EXTRACTORS = {
    "identity": _extract_identity,
    "address_proof": _extract_address_proof,
    "form16": _extract_form16,
    "salary_slip": _extract_salary_slip,
    "bank_statement": _extract_bank_statement,
    "sale_deed": _extract_sale_deed,
    "encumbrance_certificate": _extract_encumbrance_certificate,
    "property_valuation": _extract_property_valuation,
    "legal_opinion": _extract_legal_opinion,
}


def extract_entities(path: str, doc_type: str) -> dict:
    """Extract structured entities from a single PDF document.

    Uses embedded text (fast path) with Tesseract OCR as fallback for image-only scans.
    Returns a dict of fields; None means the field was not found in the document.
    """
    text = _doc_text(path)
    extractor = _EXTRACTORS.get(doc_type, _extract_generic)
    result = extractor(text)
    result["_raw_text_len"] = len(text)
    result["_path"] = path
    return result
