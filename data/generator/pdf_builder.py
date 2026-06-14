"""Build clean, internally-consistent synthetic financial PDFs with PyMuPDF (fitz).

These are the *clean* baseline documents. `tamper.py` takes the output and forges specific
signals into it. Everything here is synthetic — there is no real PII anywhere.

Design notes for downstream phases:
- Body text uses the built-in `helv` font. When `tamper.py` injects a figure in a different
  font (e.g. `tiro`/`cour`), Phase 1 can flag the font inconsistency.
- Metadata (producer/creator/creation/mod dates) is set explicitly so it can be forged later.
- Layout positions are deterministic so "same template" packets are structurally identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF

# A4 in points.
PAGE_W, PAGE_H = 595.0, 842.0
MARGIN_X = 60.0

# Built-in Base-14 font aliases used across the generator.
FONT_BODY = "helv"
FONT_BOLD = "hebo"
FONT_ALT = "tiro"   # used by tamper.py to create a font inconsistency
FONT_MONO = "cour"


@dataclass
class DocMeta:
    """PDF document metadata. Defaults look like a legitimately produced statement."""

    producer: str = "TrustShield SynthGen 1.0"
    creator: str = "TrustShield SynthGen 1.0"
    author: str = "Issuing Institution"
    title: str = "Financial Document"
    creation_date: Optional[datetime] = None
    mod_date: Optional[datetime] = None
    keywords: str = ""


def _pdf_date(dt: Optional[datetime]) -> str:
    """Format a datetime as a PDF date string, e.g. D:20240115093000+00'00'."""
    if dt is None:
        return ""
    return "D:" + dt.strftime("%Y%m%d%H%M%S") + "+00'00'"


def apply_metadata(doc: "fitz.Document", meta: DocMeta) -> None:
    """Write metadata onto a document. mod_date defaults to creation_date when unset."""
    mod = meta.mod_date or meta.creation_date
    doc.set_metadata(
        {
            "producer": meta.producer,
            "creator": meta.creator,
            "author": meta.author,
            "title": meta.title,
            "subject": meta.title,
            "keywords": meta.keywords,
            "creationDate": _pdf_date(meta.creation_date),
            "modDate": _pdf_date(mod),
        }
    )


def _lines(
    page: "fitz.Page",
    start_y: float,
    rows: list[str],
    *,
    x: float = MARGIN_X,
    leading: float = 18.0,
    font: str = FONT_BODY,
    size: float = 11.0,
    color: tuple = (0, 0, 0),
) -> float:
    """Write a list of text rows top-to-bottom; return the y after the last row."""
    y = start_y
    for row in rows:
        page.insert_text((x, y), row, fontname=font, fontsize=size, color=color)
        y += leading
    return y


def _header(page: "fitz.Page", title: str, subtitle: str = "") -> float:
    page.insert_text((MARGIN_X, 70), title, fontname=FONT_BOLD, fontsize=18, color=(0.05, 0.1, 0.3))
    page.draw_line((MARGIN_X, 84), (PAGE_W - MARGIN_X, 84), color=(0.05, 0.1, 0.3), width=1.2)
    y = 110
    if subtitle:
        page.insert_text((MARGIN_X, y), subtitle, fontname=FONT_BODY, fontsize=10, color=(0.3, 0.3, 0.3))
        y += 24
    return y


def _money(amount: float) -> str:
    """Indian-style currency string, e.g. ₹18,40,000."""
    s = f"{int(round(amount)):,}"  # plain grouping; fine for a synthetic demo
    return f"Rs. {s}"


def _new_doc() -> tuple["fitz.Document", "fitz.Page"]:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    return doc, page


# --------------------------------------------------------------------------------------
# Document builders. Each returns an open fitz.Document; the caller saves it.
# --------------------------------------------------------------------------------------
def build_identity(name: str, pan: str, dob: str, meta: DocMeta) -> "fitz.Document":
    doc, page = _new_doc()
    y = _header(page, "INCOME TAX DEPARTMENT", "Permanent Account Number Card")
    _lines(
        page,
        y + 6,
        [
            "",
            f"Name:            {name}",
            f"PAN:             {pan}",
            f"Date of Birth:   {dob}",
            "Signature:       ____________________",
        ],
        leading=22,
        size=12,
    )
    meta.title = "PAN Card"
    apply_metadata(doc, meta)
    return doc


def build_form16(
    name: str, pan: str, employer: str, gross_income: float, tax_paid: float, fy: str, meta: DocMeta
) -> "fitz.Document":
    doc, page = _new_doc()
    y = _header(page, "FORM 16", f"Certificate of TDS  |  FY {fy}")
    y = _lines(
        page,
        y + 6,
        [
            f"Employee:        {name}",
            f"PAN:             {pan}",
            f"Employer:        {employer}",
            "",
            "Part B - Details of Salary Paid",
        ],
        leading=20,
        size=11,
    )
    # The headline income figure — tamper.py targets this row's rectangle.
    page.insert_text((MARGIN_X, y + 8), "Gross Salary (Annual):", fontname=FONT_BODY, fontsize=12)
    page.insert_text((320, y + 8), _money(gross_income), fontname=FONT_BODY, fontsize=12)
    page.insert_text((MARGIN_X, y + 34), "Total Tax Deducted (TDS):", fontname=FONT_BODY, fontsize=12)
    page.insert_text((320, y + 34), _money(tax_paid), fontname=FONT_BODY, fontsize=12)
    meta.title = "Form 16"
    apply_metadata(doc, meta)
    return doc


def build_salary_slip(
    name: str, employer: str, month: str, net_monthly: float, meta: DocMeta
) -> "fitz.Document":
    doc, page = _new_doc()
    y = _header(page, "SALARY SLIP", f"{employer}  |  {month}")
    basic = net_monthly * 0.5
    hra = net_monthly * 0.3
    allow = net_monthly * 0.2
    y = _lines(
        page,
        y + 6,
        [
            f"Employee:        {name}",
            "",
            f"Basic Pay:               {_money(basic)}",
            f"HRA:                     {_money(hra)}",
            f"Special Allowance:       {_money(allow)}",
        ],
        leading=20,
        size=11,
    )
    page.insert_text((MARGIN_X, y + 10), "Net Pay (Monthly):", fontname=FONT_BOLD, fontsize=13)
    page.insert_text((320, y + 10), _money(net_monthly), fontname=FONT_BOLD, fontsize=13)
    meta.title = "Salary Slip"
    apply_metadata(doc, meta)
    return doc


def build_bank_statement(
    name: str,
    account_number: str,
    monthly_credit: float,
    months: list[str],
    meta: DocMeta,
    *,
    duplicate_row: bool = False,
) -> "fitz.Document":
    """Six-month statement. If duplicate_row, one salary-credit row is duplicated verbatim
    (a classic forged-statement padding signal Phase 1 can detect)."""
    doc, page = _new_doc()
    masked_acct = account_number[:2] + "XXXX" + account_number[-4:]
    y = _header(page, "BANK STATEMENT", f"Account: {masked_acct}  |  Holder: {name}")
    rows = ["Date          Description                         Credit"]
    balance = 0.0
    for m in months:
        rows.append(f"{m}-28   SALARY CREDIT {name.split()[0].upper():<18}   {_money(monthly_credit)}")
    if duplicate_row and months:
        # Verbatim duplicate of the first month's salary credit — padding the inflows.
        m = months[0]
        rows.append(f"{m}-28   SALARY CREDIT {name.split()[0].upper():<18}   {_money(monthly_credit)}")
    _lines(page, y + 6, rows, leading=18, size=10, font=FONT_MONO)
    meta.title = "Bank Statement"
    apply_metadata(doc, meta)
    return doc


def make_seal_png() -> bytes:
    """A small deterministic grayscale 'bank seal' PNG. Duplicating this is a copy-paste signal."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 72, 72))
    pix.clear_with(180)  # solid gray block; identical bytes every time
    return pix.tobytes("png")


# --------------------------------------------------------------------------------------
# Legal & land-record builders (secured-lending collateral docs)
# --------------------------------------------------------------------------------------
def build_sale_deed(
    owner_name: str, pan: str, property_id: str, address: str, consideration: float,
    seller_name: str, meta: DocMeta,
) -> "fitz.Document":
    """Property title / ownership-transfer deed. `owner_name` is the current owner (the loan
    applicant for a clean packet). Tampering targets the owner-name or property-id rows."""
    doc, page = _new_doc()
    y = _header(page, "SALE DEED", "Office of the Sub-Registrar")
    _lines(
        page,
        y + 6,
        [
            f"Document No:     SD/2023/{property_id.replace('/', '')}",
            f"Property No:     {property_id}",
            f"Property Addr:   {address}",
            "",
            f"Seller (Vendor): {seller_name}",
            f"Owner (Vendee):  {owner_name}",
            f"PAN of Vendee:   {pan}",
            f"Consideration:   {_money(consideration)}",
            "",
            "Registered and executed before the Sub-Registrar.",
        ],
        leading=20,
        size=11,
    )
    meta.title = "Sale Deed"
    apply_metadata(doc, meta)
    return doc


def build_encumbrance_certificate(
    owner_name: str, property_id: str, address: str, charges: list[dict], period: str, meta: DocMeta,
) -> "fitz.Document":
    """EC listing registered charges on the property. Empty `charges` => 'NIL ENCUMBRANCES'.
    A forged EC (tamper) white-boxes a real charge row and stamps NIL on top."""
    doc, page = _new_doc()
    y = _header(page, "ENCUMBRANCE CERTIFICATE", f"Property: {property_id}  |  Period: {period}")
    rows = [
        f"Owner:           {owner_name}",
        f"Property Addr:   {address}",
        "",
        "Registered transactions / charges:",
    ]
    if charges:
        for c in charges:
            rows.append(
                f"  - {c.get('type', 'mortgage')} in favour of {c.get('lender', 'Bank')}, "
                f"{_money(c.get('amount', 0))}, registered {c.get('registered_on', 'NA')}"
            )
    else:
        rows.append("  NIL ENCUMBRANCES REGISTERED FOR THE PERIOD.")
    _lines(page, y + 6, rows, leading=19, size=11)
    meta.title = "Encumbrance Certificate"
    apply_metadata(doc, meta)
    return doc


def build_property_valuation(
    owner_name: str, property_id: str, address: str, valued_amount: float, meta: DocMeta,
) -> "fitz.Document":
    """Valuer's market-value report. The headline figure is what `valuation_inflation` inflates."""
    doc, page = _new_doc()
    y = _header(page, "PROPERTY VALUATION REPORT", "Approved Valuer's Assessment")
    y = _lines(
        page,
        y + 6,
        [
            f"Property No:     {property_id}",
            f"Property Addr:   {address}",
            f"Owner:           {owner_name}",
            f"Valuer:          M/s Apex Valuers (Reg. CAT-I/2018/441)",
            "",
        ],
        leading=20,
        size=11,
    )
    page.insert_text((MARGIN_X, y + 8), "Assessed Market Value:", fontname=FONT_BOLD, fontsize=13)
    page.insert_text((320, y + 8), _money(valued_amount), fontname=FONT_BOLD, fontsize=13)
    meta.title = "Property Valuation"
    apply_metadata(doc, meta)
    return doc


def build_legal_opinion(
    owner_name: str, property_id: str, advocate: str, clear: bool, meta: DocMeta,
) -> "fitz.Document":
    """Advocate's title-search opinion. `clear` toggles the conclusion."""
    doc, page = _new_doc()
    y = _header(page, "LEGAL OPINION", "Title Search & Search Report")
    conclusion = (
        "The title is clear, marketable and free from reasonable doubt; the property can be "
        "accepted as security."
        if clear
        else "The title is NOT clear; defects were observed. Property should not be accepted as security."
    )
    _lines(
        page,
        y + 6,
        [
            f"Property No:     {property_id}",
            f"Owner examined:  {owner_name}",
            f"Advocate:        {advocate} (Bar Reg. KAR/2015/3321)",
            "",
            "Opinion:",
            f"  {conclusion}",
        ],
        leading=20,
        size=11,
    )
    meta.title = "Legal Opinion"
    apply_metadata(doc, meta)
    return doc
