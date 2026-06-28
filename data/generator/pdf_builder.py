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
# Field map — records WHERE each editable value sits so the image pipeline can target it
# with a seamless, field-aware edit (instead of a blind random box). `fraud` is the
# realistic attacker direction. Rects are in PDF points; the raster step scales by dpi/72.
# --------------------------------------------------------------------------------------
def _text_rect(x: float, y: float, value: str, font: str, size: float) -> tuple[float, float, float, float]:
    """Glyph bounding box (PDF points) for text drawn by `insert_text` at baseline (x, y).
    PyMuPDF places the baseline at y; glyphs rise ~0.8·size above it and drop ~0.22·size below."""
    w = fitz.get_text_length(value, fontname=font, fontsize=size)
    return (x - 1.0, y - size * 0.80, x + w + 1.0, y + size * 0.22)


def _record_field(fields: Optional[dict], name: str, x: float, y: float, value: str,
                  *, font: str = FONT_BODY, size: float = 11.0, fraud: str = "none",
                  kind: str = "text", amount: Optional[float] = None) -> None:
    if fields is None:
        return
    fields[name] = {
        "rect_pts": [round(v, 2) for v in _text_rect(x, y, value, font, size)],
        "value": value, "amount": amount, "font": font, "size": size,
        "fraud": fraud, "kind": kind,
    }


def _money_field(page: "fitz.Page", x: float, y: float, amount: float, *, size: float = 8.5,
                 font: str = FONT_BODY, fields: Optional[dict] = None, name: str = "",
                 fraud: str = "none") -> None:
    """Draw a currency value with `insert_text` (so its glyph rect is exactly known) + record it."""
    s = _money(amount)
    page.insert_text((x, y), s, fontname=font, fontsize=size)
    if name:
        _record_field(fields, name, x, y, s, font=font, size=size, fraud=fraud,
                      kind="money", amount=float(amount))


def _htext(page: "fitz.Page", x0: float, x1: float, baseline_y: float, text: str, *,
           size: float = 8.0, bold: bool = False, color: tuple = (0, 0, 0), align: int = 0) -> None:
    """Single line drawn with `insert_text` (reliable in short cells, unlike `insert_textbox`).
    align: 0=left, 1=center, 2=right within [x0, x1]."""
    font = FONT_BOLD if bold else FONT_BODY
    tw = fitz.get_text_length(text, fontname=font, fontsize=size)
    if align == 1:
        tx = x0 + (x1 - x0 - tw) / 2
    elif align == 2:
        tx = x1 - tw
    else:
        tx = x0
    page.insert_text((tx, baseline_y), text, fontname=font, fontsize=size, color=color)


def _cell(page: "fitz.Page", rect: "fitz.Rect", text: str = "", *, size: float = 8.0,
          bold: bool = False, align: int = 0, pad: float = 3.0, color: tuple = (0, 0, 0),
          border: float = 0.6) -> None:
    """A bordered table cell with (optionally centered/right-aligned) single-line text."""
    if border:
        page.draw_rect(rect, color=(0.45, 0.45, 0.45), width=border)
    if text:
        ty = rect.y0 + (rect.height + size * 0.72) / 2 - size * 0.1
        _htext(page, rect.x0 + pad, rect.x1 - pad, ty, text, size=size, bold=bold, color=color, align=align)


def _assessment_year(fy: str) -> str:
    """FY '2023-24' → AY '2024-25'."""
    try:
        start = int(fy.split("-")[0])
        return f"{start + 1}-{str(start + 2)[-2:]}"
    except Exception:
        return "2024-25"


# Form-16 employer/template variants — different issuers print slightly different headers, TANs and
# addresses; rotating them kills the single-template fingerprint the old generator had.
_F16_TEMPLATES: list[dict] = [
    {"band": (0.12, 0.20, 0.42), "tan": "BLRT04321A", "cert": "TRA2K7QF",
     "addr": ["Electronics City Phase 1", "Bengaluru, Karnataka - 560100"], "updated": "21-May-2024"},
    {"band": (0.10, 0.32, 0.28), "tan": "MUMW09887C", "cert": "PQRS9912",
     "addr": ["Plot 12, MIDC Andheri (E)", "Mumbai, Maharashtra - 400093"], "updated": "14-Jun-2024"},
    {"band": (0.30, 0.16, 0.14), "tan": "DELH03210B", "cert": "ZX8810KK",
     "addr": ["Tower B, Cyber Hub, DLF Ph-2", "Gurugram, Haryana - 122002"], "updated": "02-Jun-2024"},
]

# A larger pool of issuer header bands + brand palettes the layout-family generator samples from, so the
# image dataset never repeats one Form-16/bank/payslip "look". Monochrome entries (band=None) too.
_BANDS: list[Optional[tuple]] = [
    (0.12, 0.20, 0.42), (0.10, 0.32, 0.28), (0.30, 0.16, 0.14), (0.16, 0.16, 0.18),
    (0.20, 0.30, 0.46), (0.36, 0.22, 0.10), (0.08, 0.36, 0.40), None, None, (0.28, 0.10, 0.32),
]


def _rng_choice(rng, seq):
    """np.random.Generator-safe choice that returns the element (not a 0-d array)."""
    return seq[int(rng.integers(0, len(seq)))]


def _form16_layout(rng) -> dict:
    """A seeded Form-16 layout *family* — structural variety (format, column widths, row counts, fonts,
    bands, wording) so the model can't memorize one layout. Field boxes stay exact because every value is
    still drawn through `_money_field`/`_record_field`."""
    style = int(rng.integers(0, 3))                       # 3 structural formats
    body = float(round(rng.uniform(7.5, 9.0), 1))
    rh = float(round(rng.uniform(13.0, 16.5), 1))
    # quarterly table: randomize the two interior column splits + an optional receipt-number column
    q_split1 = float(rng.uniform(60, 85))                 # width of the "Quarter" column (pts)
    q_split2 = float(rng.uniform(170, 230))               # width of the "Amount paid" column
    receipt_col = bool(rng.integers(0, 2))
    amt_col_w = float(rng.uniform(95, 135))               # Part-B amount column width
    band = _rng_choice(rng, _BANDS)
    # Part-B: a randomized set of optional rows → variable row count + varied positions for edits
    optional = [
        ("perquisites", "Add: Value of perquisites u/s 17(2)", 0.04, "inflate"),
        ("profits_lieu", "Add: Profits in lieu of salary u/s 17(3)", 0.02, "inflate"),
        ("hra_detail", "Less: House Rent Allowance u/s 10(13A)", 0.05, "none"),
        ("ded_80c", "Less: Deduction u/s 80C", 0.045, "inflate"),
        ("ded_80d", "Less: Deduction u/s 80D (medical)", 0.012, "inflate"),
        ("ded_80ccd", "Less: Deduction u/s 80CCD(1B) (NPS)", 0.01, "inflate"),
        ("rebate_87a", "Less: Rebate u/s 87A", 0.005, "none"),
        ("cess", "Add: Health & Education Cess @ 4%", 0.006, "none"),
        ("surcharge", "Add: Surcharge", 0.008, "inflate"),
    ]
    n_opt = int(rng.integers(2, 6))
    idx = rng.permutation(len(optional))[:n_opt]
    chosen = [optional[i] for i in sorted(idx)]
    watermark = _rng_choice(rng, ["TRACES", "TRACES", "INCOME TAX", "FORM 16", ""])
    title = _rng_choice(rng, ["FORM NO. 16", "FORM NO. 16", "FORM 16"])
    return {"style": style, "body": body, "rh": rh, "q_split1": q_split1, "q_split2": q_split2,
            "receipt_col": receipt_col, "amt_col_w": amt_col_w, "band": band, "optional": chosen,
            "watermark": watermark, "title": title,
            "cert": "".join(_rng_choice(rng, list("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789")) for _ in range(8)),
            "tan": "".join(_rng_choice(rng, list("ABCDEFGHJKLMNPQRSTUVWXYZ")) for _ in range(4))
                   + "".join(str(int(rng.integers(0, 10))) for _ in range(5)) + _rng_choice(rng, list("ABCDEFGH")),
            "addr": _rng_choice(rng, [t["addr"] for t in _F16_TEMPLATES]),
            "updated": _rng_choice(rng, ["21-May-2024", "14-Jun-2024", "02-Jun-2024", "30-Apr-2024", "11-Jul-2024"])}


# --------------------------------------------------------------------------------------
# Document builders. Each returns an open fitz.Document; the caller saves it. Builders that
# back the image-tamper pipeline also accept an optional `fields` out-dict (see field map above).
# --------------------------------------------------------------------------------------
def _id_rows(page: "fitz.Page", y: float, rows: list[tuple], fields: Optional[dict],
             *, vx: float = MARGIN_X + 140, leading: float = 30.0) -> float:
    """Label/value rows where each value sits at a known x (so its glyph rect is exact + recordable).
    `rows` items: (label, value, field_name | "", fraud, font, size, kind)."""
    for label, val, fname, fraud, font, size, kind in rows:
        page.insert_text((MARGIN_X, y), label + ":", fontname=FONT_BODY, fontsize=11, color=(0.25, 0.25, 0.25))
        page.insert_text((vx, y), val, fontname=font, fontsize=size)
        if fname:
            _record_field(fields, fname, vx, y, val, font=font, size=size, fraud=fraud, kind=kind)
        y += leading
    return y


def build_identity(name: str, pan: str, dob: str, meta: DocMeta, *,
                   fields: Optional[dict] = None, father: str = "") -> "fitz.Document":
    """PAN card (doc-style). `fields` records the image-targetable fraud fields (pan, name, dob)."""
    doc, page = _new_doc()
    y = _header(page, "INCOME TAX DEPARTMENT", "Permanent Account Number Card")
    y = _id_rows(page, y + 24, [
        ("Name", name, "name", "swap", FONT_BODY, 12, "text"),
        ("Father's Name", father or "—", "", "none", FONT_BODY, 12, "text"),
        ("Date of Birth", dob, "dob", "swap", FONT_BODY, 12, "date"),
        ("Permanent Account No.", pan, "pan", "swap", FONT_BOLD, 13, "pan"),
    ], fields)
    page.insert_text((MARGIN_X, y + 12), "Signature: ____________________", fontname=FONT_BODY, fontsize=11)
    meta.title = "PAN Card"
    apply_metadata(doc, meta)
    return doc


def build_aadhaar(name: str, aadhaar: str, dob: str, gender: str, address: list[str], meta: DocMeta,
                  *, fields: Optional[dict] = None) -> "fitz.Document":
    """Aadhaar (doc-style, clearly marked SYNTHETIC — never a usable ID). `fields` records the fraud
    fields (aadhaar_number, name, dob)."""
    doc, page = _new_doc()
    y = _header(page, "GOVERNMENT OF INDIA", "Unique Identification Authority of India (UIDAI)")
    page.insert_textbox(fitz.Rect(110, 300, 490, 400), "SPECIMEN", fontname=FONT_BOLD, fontsize=72,
                        color=(0.93, 0.93, 0.93), align=1)
    y = _id_rows(page, y + 24, [
        ("Name", name, "name", "swap", FONT_BODY, 12, "text"),
        ("Date of Birth", dob, "dob", "swap", FONT_BODY, 12, "date"),
        ("Gender", gender, "", "none", FONT_BODY, 12, "text"),
        ("Aadhaar No.", aadhaar, "aadhaar_number", "swap", FONT_BOLD, 14, "aadhaar"),
    ], fields)
    page.insert_text((MARGIN_X, y), "Address:", fontname=FONT_BODY, fontsize=11, color=(0.25, 0.25, 0.25))
    _lines(page, y + 16, address, x=MARGIN_X + 16, leading=16, size=10)
    page.insert_textbox(fitz.Rect(MARGIN_X, PAGE_H - 70, PAGE_W - MARGIN_X, PAGE_H - 50),
                        "Synthetic specimen generated for tamper-detection research - not a real Aadhaar.",
                        fontname=FONT_BODY, fontsize=8, color=(0.5, 0.5, 0.5), align=1)
    meta.title = "Aadhaar"
    apply_metadata(doc, meta)
    return doc


def build_form16(
    name: str, pan: str, employer: str, gross_income: float, tax_paid: float, fy: str, meta: DocMeta,
    *, fields: Optional[dict] = None, template: int = 0,
) -> "fitz.Document":
    """A TRACES-style Form 16: Part A (employer/employee, PAN/TAN, quarterly-TDS table) + Part B
    (salary breakup). The headline gross-salary figure is still drawn as `_money(gross_income)` so the
    PDF-level `tamper.edit_money_figure` keeps working; `fields` (if given) records the image-targetable
    fraud fields (gross_salary, tds, employer_pan)."""
    doc, page = _new_doc()
    ML, MR = 40.0, PAGE_W - 40.0
    midx = (ML + MR) / 2
    tpl = _F16_TEMPLATES[template % len(_F16_TEMPLATES)]
    ay = _assessment_year(fy)
    fy_from, fy_to = f"01-Apr-{fy.split('-')[0]}", f"31-Mar-{int(fy.split('-')[0]) + 1}"

    # faint TRACES watermark behind the body
    page.insert_textbox(fitz.Rect(110, 360, 490, 470), "TRACES", fontname=FONT_BOLD, fontsize=78,
                        color=(0.92, 0.92, 0.92), align=1)

    # ── top header ───────────────────────────────────────────────────────────────────
    _htext(page, ML, MR, 50, "FORM NO. 16", size=11, bold=True, align=1)
    _htext(page, ML, MR, 62, "[See rule 31(1)(a)]", size=8, align=1)
    _htext(page, ML, MR, 82,
           "Certificate under Section 203 of the Income-tax Act, 1961 for tax deducted at source on salary",
           size=8.5, align=1)

    # ── PART A banner + certificate row ──────────────────────────────────────────────
    y = 102.0
    page.draw_rect(fitz.Rect(ML, y, MR, y + 15), color=tpl["band"], fill=tpl["band"])
    _htext(page, ML, MR, y + 10.5, "PART A", size=9, bold=True, color=(1, 1, 1), align=1)
    y += 15
    _cell(page, fitz.Rect(ML, y, MR, y + 15))
    page.insert_text((ML + 5, y + 10), f"Certificate No.  {tpl['cert']}", fontname=FONT_BODY, fontsize=8)
    page.insert_text((MR - 165, y + 10), f"Last updated on  {tpl['updated']}", fontname=FONT_BODY, fontsize=8)
    y += 15

    # employer / employee two-column block
    bh = 58.0
    _cell(page, fitz.Rect(ML, y, midx, y + bh))
    _cell(page, fitz.Rect(midx, y, MR, y + bh))
    page.insert_text((ML + 5, y + 11), "Name and address of the Employer", fontname=FONT_BOLD, fontsize=7.5)
    _lines(page, y + 23, [employer, *tpl["addr"]], x=ML + 5, leading=11, size=8)
    page.insert_text((midx + 5, y + 11), "Name and address of the Employee", fontname=FONT_BOLD, fontsize=7.5)
    page.insert_text((midx + 5, y + 23), name, fontname=FONT_BODY, fontsize=8)
    y += bh

    # PAN-of-deductor | TAN-of-deductor | PAN-of-employee  (3-col header + value row)
    c1, c2 = ML + (MR - ML) / 3, ML + 2 * (MR - ML) / 3
    _cell(page, fitz.Rect(ML, y, c1, y + 13), "PAN of the Deductor", size=7.5, align=1)
    _cell(page, fitz.Rect(c1, y, c2, y + 13), "TAN of the Deductor", size=7.5, align=1)
    _cell(page, fitz.Rect(c2, y, MR, y + 13), "PAN of the Employee", size=7.5, align=1)
    y += 13
    _cell(page, fitz.Rect(ML, y, c1, y + 15))
    _cell(page, fitz.Rect(c1, y, c2, y + 15))
    _cell(page, fitz.Rect(c2, y, MR, y + 15))
    deductor_pan = pan[:3] + "CD" + pan[5:]  # a distinct (synthetic) employer PAN
    page.insert_text((ML + 6, y + 10.5), deductor_pan, fontname=FONT_BODY, fontsize=8.5)
    _record_field(fields, "employer_pan", ML + 6, y + 10.5, deductor_pan, font=FONT_BODY, size=8.5,
                  fraud="swap", kind="pan")
    page.insert_text((c1 + 6, y + 10.5), tpl["tan"], fontname=FONT_BODY, fontsize=8.5)
    page.insert_text((c2 + 6, y + 10.5), pan, fontname=FONT_BODY, fontsize=8.5)
    y += 15

    # AY | period row
    _cell(page, fitz.Rect(ML, y, midx, y + 15), f"  Assessment Year:  {ay}", size=8)
    _cell(page, fitz.Rect(midx, y, MR, y + 15), f"  Period:  {fy_from}  to  {fy_to}", size=8)
    y += 15

    # ── Part A summary: quarterly TDS table ──────────────────────────────────────────
    y += 6
    page.insert_text((ML, y), "Summary of tax deducted at source", fontname=FONT_BOLD, fontsize=8)
    y += 5
    qx = [ML, ML + 70, ML + 250, MR]  # Quarter | Amount paid/credited | Tax deducted/deposited
    hdr = ["Quarter", "Amount paid / credited", "Amount of tax deducted & deposited"]
    rh = 13.0
    for i, h in enumerate(hdr):
        _cell(page, fitz.Rect(qx[i], y, qx[i + 1], y + rh), h, size=7.5, bold=True, align=1)
    y += rh
    q_gross, q_tax = gross_income / 4.0, tax_paid / 4.0
    for qi, q in enumerate(("Q1", "Q2", "Q3", "Q4"), start=0):
        _cell(page, fitz.Rect(qx[0], y, qx[1], y + rh), q, size=8, align=1)
        _cell(page, fitz.Rect(qx[1], y, qx[2], y + rh))
        _cell(page, fitz.Rect(qx[2], y, qx[3], y + rh))
        _money_field(page, qx[1] + 6, y + 9.5, round(q_gross), size=8)
        _money_field(page, qx[2] + 6, y + 9.5, round(q_tax), size=8)
        y += rh
    # total row (gross + tax appear here as `_money(...)` so the legacy PDF edit still finds them)
    _cell(page, fitz.Rect(qx[0], y, qx[1], y + rh), "Total", size=8, bold=True, align=1)
    _cell(page, fitz.Rect(qx[1], y, qx[2], y + rh))
    _cell(page, fitz.Rect(qx[2], y, qx[3], y + rh))
    _money_field(page, qx[1] + 6, y + 9.5, gross_income, size=8, font=FONT_BOLD)
    _money_field(page, qx[2] + 6, y + 9.5, tax_paid, size=8, font=FONT_BOLD)
    y += rh

    # ── PART B banner + salary breakup ───────────────────────────────────────────────
    y += 14
    page.draw_rect(fitz.Rect(ML, y, MR, y + 15), color=tpl["band"], fill=tpl["band"])
    _htext(page, ML, MR, y + 10.5, "PART B (Annexure)", size=9, bold=True, color=(1, 1, 1), align=1)
    y += 15
    _cell(page, fitz.Rect(ML, y, MR, y + 14), "  Details of Salary Paid and Tax Deducted", size=8, bold=True)
    y += 14

    std_ded, prof_tax = 50000.0, 2400.0
    chap_via = round(gross_income * 0.08)
    exempt = round(gross_income * 0.06)
    net_salary = gross_income - exempt
    chargeable = net_salary - std_ded - prof_tax
    taxable = max(0.0, chargeable - chap_via)
    amt_x = MR - 110  # left edge of the amount column (values left-aligned here → exact rects)
    rows = [
        ("1.  Gross Salary  [Sec 17(1)]", gross_income, "gross_salary", "inflate", False),
        ("2.  Less: Allowances exempt u/s 10 (HRA, LTA)", exempt, "exempt_s10", "none", False),
        ("3.  Net Salary", net_salary, "", "none", False),
        ("4.  Less: Standard deduction u/s 16(ia)", std_ded, "", "none", False),
        ("5.  Less: Tax on employment u/s 16(iii)", prof_tax, "", "none", False),
        ("6.  Income chargeable under head 'Salaries'", chargeable, "", "none", False),
        ("7.  Less: Deductions under Chapter VI-A (80C, 80D)", chap_via, "chapter_via", "inflate", False),
        ("8.  Total taxable income", taxable, "", "none", True),
        ("9.  Tax payable on total income", round(taxable * 0.15), "", "none", False),
        ("10. Tax deducted at source (TDS)", tax_paid, "tds", "inflate", True),
    ]
    rh = 15.0
    for label, amount, fname, fraud, bold in rows:
        _cell(page, fitz.Rect(ML, y, amt_x, y + rh), "  " + label, size=8, bold=bold)
        _cell(page, fitz.Rect(amt_x, y, MR, y + rh))
        _money_field(page, amt_x + 6, y + 10, amount, size=8.5, font=(FONT_BOLD if bold else FONT_BODY),
                     fields=fields if fname else None, name=fname, fraud=fraud)
        y += rh

    # attestation
    y += 16
    page.insert_textbox(fitz.Rect(ML, y, MR, y + 26),
                        "I certify that the information given above is true, complete and correct and is "
                        "based on the books of account, documents, TDS statements and other available records.",
                        fontname=FONT_BODY, fontsize=7.5)
    page.insert_text((MR - 150, y + 44), "Signature of person responsible", fontname=FONT_BODY, fontsize=8)

    meta.title = "Form 16"
    apply_metadata(doc, meta)
    return doc


def build_form16_v2(
    name: str, pan: str, employer: str, gross_income: float, tax_paid: float, fy: str, meta: DocMeta,
    *, fields: Optional[dict] = None, rng=None,
) -> "fitz.Document":
    """Layout-FAMILY Form 16 for the image dataset (Part 1). Driven by `_form16_layout(rng)` → variable
    formats, column widths, row counts, fonts, bands and wording. Every numeric/text value is drawn via
    `_money_field`/`_record_field`, so its field box stays pixel-exact for seamless edits + masks. Records
    MANY editable fields (every quarterly cell + every Part-B money row) so edits land across the page."""
    import numpy as _np
    rng = rng if rng is not None else _np.random.default_rng()
    L = _form16_layout(rng)
    doc, page = _new_doc()
    ML, MR = 40.0, PAGE_W - 40.0
    midx = (ML + MR) / 2
    band = L["band"]
    band_fill = band if band is not None else (0.85, 0.85, 0.85)
    band_txt = (1, 1, 1) if band is not None else (0.1, 0.1, 0.1)
    ay = _assessment_year(fy)
    fy_from, fy_to = f"01-Apr-{fy.split('-')[0]}", f"31-Mar-{int(fy.split('-')[0]) + 1}"
    bs, rh = L["body"], L["rh"]

    if L["watermark"]:
        page.insert_textbox(fitz.Rect(110, 360, 490, 470), L["watermark"], fontname=FONT_BOLD, fontsize=78,
                            color=(0.92, 0.92, 0.92), align=1)

    _htext(page, ML, MR, 50, L["title"], size=11, bold=True, align=1)
    _htext(page, ML, MR, 62, "[See rule 31(1)(a)]", size=8, align=1)
    _htext(page, ML, MR, 82,
           "Certificate under Section 203 of the Income-tax Act, 1961 for tax deducted at source on salary",
           size=8.5, align=1)

    y = 102.0
    page.draw_rect(fitz.Rect(ML, y, MR, y + 15), color=band_fill, fill=band_fill)
    _htext(page, ML, MR, y + 10.5, "PART A", size=9, bold=True, color=band_txt, align=1)
    y += 15
    _cell(page, fitz.Rect(ML, y, MR, y + 15))
    page.insert_text((ML + 5, y + 10), f"Certificate No.  {L['cert']}", fontname=FONT_BODY, fontsize=bs)
    page.insert_text((MR - 165, y + 10), f"Last updated on  {L['updated']}", fontname=FONT_BODY, fontsize=bs)
    y += 15

    bh = 58.0
    _cell(page, fitz.Rect(ML, y, midx, y + bh))
    _cell(page, fitz.Rect(midx, y, MR, y + bh))
    page.insert_text((ML + 5, y + 11), "Name and address of the Employer", fontname=FONT_BOLD, fontsize=7.5)
    _lines(page, y + 23, [employer, *L["addr"]], x=ML + 5, leading=11, size=bs)
    page.insert_text((midx + 5, y + 11), "Name and address of the Employee", fontname=FONT_BOLD, fontsize=7.5)
    page.insert_text((midx + 5, y + 23), name, fontname=FONT_BODY, fontsize=bs)
    y += bh

    c1, c2 = ML + (MR - ML) / 3, ML + 2 * (MR - ML) / 3
    _cell(page, fitz.Rect(ML, y, c1, y + 13), "PAN of the Deductor", size=7.5, align=1)
    _cell(page, fitz.Rect(c1, y, c2, y + 13), "TAN of the Deductor", size=7.5, align=1)
    _cell(page, fitz.Rect(c2, y, MR, y + 13), "PAN of the Employee", size=7.5, align=1)
    y += 13
    _cell(page, fitz.Rect(ML, y, c1, y + 15)); _cell(page, fitz.Rect(c1, y, c2, y + 15)); _cell(page, fitz.Rect(c2, y, MR, y + 15))
    deductor_pan = pan[:3] + "CD" + pan[5:]
    page.insert_text((ML + 6, y + 10.5), deductor_pan, fontname=FONT_BODY, fontsize=bs)
    _record_field(fields, "employer_pan", ML + 6, y + 10.5, deductor_pan, font=FONT_BODY, size=bs, fraud="swap", kind="pan")
    page.insert_text((c1 + 6, y + 10.5), L["tan"], fontname=FONT_BODY, fontsize=bs)
    page.insert_text((c2 + 6, y + 10.5), pan, fontname=FONT_BODY, fontsize=bs)
    _record_field(fields, "employee_pan", c2 + 6, y + 10.5, pan, font=FONT_BODY, size=bs, fraud="swap", kind="pan")
    y += 15

    _cell(page, fitz.Rect(ML, y, midx, y + 15), f"  Assessment Year:  {ay}", size=bs)
    _cell(page, fitz.Rect(midx, y, MR, y + 15), f"  Period:  {fy_from}  to  {fy_to}", size=bs)
    y += 15 + 6

    page.insert_text((ML, y), "Summary of tax deducted at source", fontname=FONT_BOLD, fontsize=8)
    y += 5
    # quarterly table — variable column widths + optional receipt column
    if L["receipt_col"]:
        qx = [ML, ML + L["q_split1"], ML + L["q_split2"], MR - 90, MR]
        hdr = ["Quarter", "Amount paid / credited", "Tax deducted & deposited", "Receipt No."]
    else:
        qx = [ML, ML + L["q_split1"], ML + L["q_split2"], MR]
        hdr = ["Quarter", "Amount paid / credited", "Amount of tax deducted & deposited"]
    for i, h in enumerate(hdr):
        _cell(page, fitz.Rect(qx[i], y, qx[i + 1], y + 13), h, size=7.5, bold=True, align=1)
    y += 13
    q_gross, q_tax = gross_income / 4.0, tax_paid / 4.0
    for qi, q in enumerate(("Q1", "Q2", "Q3", "Q4")):
        for k in range(len(qx) - 1):
            _cell(page, fitz.Rect(qx[k], y, qx[k + 1], y + rh))
        _htext(page, qx[0], qx[1], y + rh * 0.62, q, size=bs, align=1)
        _money_field(page, qx[1] + 6, y + rh * 0.62, round(q_gross), size=bs, fields=fields,
                     name=f"q{qi+1}_paid", fraud="inflate")
        _money_field(page, qx[2] + 6, y + rh * 0.62, round(q_tax), size=bs, fields=fields,
                     name=f"q{qi+1}_tax", fraud="inflate")
        if L["receipt_col"]:
            page.insert_text((qx[3] + 6, y + rh * 0.62),
                             "QR" + "".join(str(int(rng.integers(0, 10))) for _ in range(6)),
                             fontname=FONT_BODY, fontsize=bs)
        y += rh
    for k in range(len(qx) - 1):
        _cell(page, fitz.Rect(qx[k], y, qx[k + 1], y + rh))
    _htext(page, qx[0], qx[1], y + rh * 0.62, "Total", size=bs, bold=True, align=1)
    _money_field(page, qx[1] + 6, y + rh * 0.62, gross_income, size=bs, font=FONT_BOLD, fields=fields,
                 name="total_paid", fraud="inflate")
    _money_field(page, qx[2] + 6, y + rh * 0.62, tax_paid, size=bs, font=FONT_BOLD, fields=fields,
                 name="total_tax", fraud="inflate")
    y += rh + 14

    page.draw_rect(fitz.Rect(ML, y, MR, y + 15), color=band_fill, fill=band_fill)
    _htext(page, ML, MR, y + 10.5, "PART B (Annexure)", size=9, bold=True, color=band_txt, align=1)
    y += 15
    _cell(page, fitz.Rect(ML, y, MR, y + 14), "  Details of Salary Paid and Tax Deducted", size=8, bold=True)
    y += 14

    exempt = round(gross_income * 0.06)
    net_salary = gross_income - exempt
    std_ded, prof_tax = 50000.0, 2400.0
    chargeable = net_salary - std_ded - prof_tax
    taxable = max(0.0, chargeable * 0.92)
    amt_x = MR - L["amt_col_w"]
    # ordered Part-B rows: core + the layout's chosen optional rows (variable count → variable positions)
    rows: list[tuple] = [("1.  Gross Salary  [Sec 17(1)]", gross_income, "gross_salary", "inflate", False)]
    for i, (key, label, frac, fraud) in enumerate(L["optional"]):
        rows.append((f"{label}", round(gross_income * frac), f"partb_{key}", fraud, False))
    rows += [
        ("Less: Allowances exempt u/s 10 (HRA, LTA)", exempt, "exempt_s10", "none", False),
        ("Net Salary", net_salary, "net_salary_b", "inflate", False),
        ("Less: Standard deduction u/s 16(ia)", std_ded, "std_ded", "none", False),
        ("Less: Tax on employment u/s 16(iii)", prof_tax, "prof_tax", "none", False),
        ("Income chargeable under head 'Salaries'", chargeable, "chargeable", "inflate", False),
        ("Total taxable income", taxable, "taxable", "inflate", True),
        ("Tax payable on total income", round(taxable * 0.15), "tax_payable", "inflate", False),
        ("Tax deducted at source (TDS)", tax_paid, "tds", "inflate", True),
    ]
    for n, (label, amount, fname, fraud, bold) in enumerate(rows, start=1):
        lbl = label if label[0].isdigit() else f"{n}.  {label}"
        _cell(page, fitz.Rect(ML, y, amt_x, y + rh), "  " + lbl, size=bs, bold=bold)
        _cell(page, fitz.Rect(amt_x, y, MR, y + rh))
        _money_field(page, amt_x + 6, y + rh * 0.66, amount, size=bs, font=(FONT_BOLD if bold else FONT_BODY),
                     fields=fields, name=fname, fraud=fraud)
        y += rh

    y += 14
    page.insert_textbox(fitz.Rect(ML, y, MR, y + 26),
                        "I certify that the information given above is true, complete and correct and is "
                        "based on the books of account, documents, TDS statements and other available records.",
                        fontname=FONT_BODY, fontsize=7.5)
    page.insert_text((MR - 150, y + 44), "Signature of person responsible", fontname=FONT_BODY, fontsize=8)
    meta.title = "Form 16"
    apply_metadata(doc, meta)
    return doc


# Bank header variants (rotated with `template`) — different issuers, IFSC and branches.
_BANKS: list[dict] = [
    {"name": "HDFC Bank Ltd.", "ifsc": "HDFC0000123", "branch": "Koramangala, Bengaluru"},
    {"name": "ICICI Bank Ltd.", "ifsc": "ICIC0000456", "branch": "Andheri East, Mumbai"},
    {"name": "State Bank of India", "ifsc": "SBIN0000789", "branch": "Connaught Place, New Delhi"},
]


def _emp_id(name: str) -> str:
    return "EMP" + str(sum(ord(c) for c in name) % 90000 + 10000)


def build_salary_slip(
    name: str, employer: str, month: str, net_monthly: float, meta: DocMeta,
    *, fields: Optional[dict] = None, template: int = 0,
) -> "fitz.Document":
    """A realistic payslip: employer header + employee details + an Earnings/Deductions table + Net Pay.
    `net_monthly` is treated as the in-hand Net Pay; gross is back-computed so deductions look real. Net
    Pay is still drawn as `_money(net_monthly)` so cross-doc checks keep matching. `fields` records the
    image-targetable fraud fields (basic, gross, net_pay)."""
    doc, page = _new_doc()
    ML, MR = 40.0, PAGE_W - 40.0
    midx = (ML + MR) / 2
    tpl = _F16_TEMPLATES[template % len(_F16_TEMPLATES)]
    net = float(net_monthly)
    gross = round(net / 0.85)                       # ~15% statutory deductions
    basic = round(gross * 0.50)
    hra = round(gross * 0.24)
    conveyance = 1600
    special = gross - basic - hra - conveyance
    ded_total = gross - round(net)
    epf = round(basic * 0.12)
    prof_tax = 200
    tds = max(0, ded_total - epf - prof_tax)

    # header band
    page.draw_rect(fitz.Rect(ML, 40, MR, 72), color=tpl["band"], fill=tpl["band"])
    _htext(page, ML + 8, MR, 56, employer, size=12, bold=True, color=(1, 1, 1))
    _htext(page, ML + 8, MR, 67, tpl["addr"][0] + ",  " + tpl["addr"][1], size=7.5, color=(0.9, 0.9, 0.9))
    _htext(page, ML, MR, 90, f"Payslip for the month of {month}", size=10, bold=True, align=1)

    # employee details — two columns of label/value
    y = 102.0
    left = [("Employee Name", name), ("Employee ID", _emp_id(name)), ("Designation", "Senior Engineer")]
    right = [("Date of Joining", "01-Jul-2019"), ("Pay Period", month), ("Days Paid", "30 / 30")]
    for (ll, lv), (rl, rv) in zip(left, right):
        page.insert_text((ML, y), f"{ll}:", fontname=FONT_BOLD, fontsize=8.5)
        page.insert_text((ML + 95, y), lv, fontname=FONT_BODY, fontsize=8.5)
        page.insert_text((midx + 10, y), f"{rl}:", fontname=FONT_BOLD, fontsize=8.5)
        page.insert_text((midx + 90, y), rv, fontname=FONT_BODY, fontsize=8.5)
        y += 15

    # Earnings | Deductions table
    y += 6
    e_amt, d_amt = midx - 80, MR - 80
    rh = 15.0
    _cell(page, fitz.Rect(ML, y, e_amt, y + rh), "  Earnings", size=8.5, bold=True)
    _cell(page, fitz.Rect(e_amt, y, midx, y + rh), "Amount  ", size=8.5, bold=True, align=2)
    _cell(page, fitz.Rect(midx, y, d_amt, y + rh), "  Deductions", size=8.5, bold=True)
    _cell(page, fitz.Rect(d_amt, y, MR, y + rh), "Amount  ", size=8.5, bold=True, align=2)
    y += rh
    earn = [("Basic", basic, "basic", "inflate"), ("House Rent Allowance", hra, "", "none"),
            ("Conveyance Allowance", conveyance, "", "none"), ("Special Allowance", special, "", "none")]
    ded = [("Provident Fund (EPF)", epf), ("Professional Tax", prof_tax),
           ("Income Tax (TDS)", tds), ("", None)]
    for (el, ev, efname, efraud), (dl, dv) in zip(earn, ded):
        _cell(page, fitz.Rect(ML, y, e_amt, y + rh), "  " + el, size=8.5)
        _cell(page, fitz.Rect(e_amt, y, midx, y + rh))
        _money_field(page, e_amt + 6, y + 10, ev, size=8.5, fields=fields if efname else None,
                     name=efname, fraud=efraud)
        _cell(page, fitz.Rect(midx, y, d_amt, y + rh), ("  " + dl) if dl else "", size=8.5)
        _cell(page, fitz.Rect(d_amt, y, MR, y + rh))
        if dv is not None:
            _money_field(page, d_amt + 6, y + 10, dv, size=8.5)
        y += rh
    # totals
    _cell(page, fitz.Rect(ML, y, e_amt, y + rh), "  Gross Earnings", size=8.5, bold=True)
    _cell(page, fitz.Rect(e_amt, y, midx, y + rh))
    _money_field(page, e_amt + 6, y + 10, gross, size=8.5, font=FONT_BOLD,
                 fields=fields, name="gross", fraud="inflate")
    _cell(page, fitz.Rect(midx, y, d_amt, y + rh), "  Total Deductions", size=8.5, bold=True)
    _cell(page, fitz.Rect(d_amt, y, MR, y + rh))
    _money_field(page, d_amt + 6, y + 10, ded_total, size=8.5, font=FONT_BOLD)
    y += rh + 8

    # Net Pay
    page.draw_rect(fitz.Rect(ML, y, MR, y + 20), color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93))
    page.insert_text((ML + 6, y + 14), "Net Pay (take-home)", fontname=FONT_BOLD, fontsize=11)
    _money_field(page, MR - 130, y + 14, net, size=11, font=FONT_BOLD,
                 fields=fields, name="net_pay", fraud="inflate")
    y += 30
    page.insert_textbox(fitz.Rect(ML, y, MR, y + 18),
                        "This is a computer-generated payslip and does not require a signature.",
                        fontname=FONT_BODY, fontsize=7.5, color=(0.4, 0.4, 0.4))
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
    fields: Optional[dict] = None,
    template: int = 0,
) -> "fitz.Document":
    """A realistic statement: bank header + account summary + a multi-row transaction table with a
    running balance (monthly salary credits + rent/UPI/ATM debits). If duplicate_row, one salary-credit
    row is duplicated verbatim (the copy-paste padding signal). `fields` records the fraud fields
    (salary_credit, closing_balance) plus the balance column so a tamper can keep the maths consistent."""
    doc, page = _new_doc()
    ML, MR = 40.0, PAGE_W - 40.0
    tpl = _F16_TEMPLATES[template % len(_F16_TEMPLATES)]
    bank = _BANKS[template % len(_BANKS)]
    masked = account_number[:2] + "XXXX" + account_number[-4:]
    first = name.split()[0].upper()

    # header band
    page.draw_rect(fitz.Rect(ML, 40, MR, 72), color=tpl["band"], fill=tpl["band"])
    _htext(page, ML + 8, MR, 56, bank["name"], size=13, bold=True, color=(1, 1, 1))
    _htext(page, ML + 8, MR, 67, f"Branch: {bank['branch']}    IFSC: {bank['ifsc']}", size=7.5,
           color=(0.9, 0.9, 0.9))
    _htext(page, ML, MR, 90, "Statement of Account", size=10, bold=True, align=1)

    # account info
    y = 100.0
    info = [("Account Holder", name), ("Account Number", masked),
            ("Account Type", "Savings"), ("Statement Period", f"{months[0]} - {months[-1]} 2024")]
    for k, v in info:
        page.insert_text((ML, y), f"{k}:", fontname=FONT_BOLD, fontsize=8.5)
        page.insert_text((ML + 110, y), v, fontname=FONT_BODY, fontsize=8.5)
        y += 14

    # build transactions + running balance
    opening = round(monthly_credit * 1.4)
    txns: list[tuple[str, str, float, float]] = []   # (date, narration, debit, credit)
    for m in months:
        txns.append((f"03-{m}", f"NEFT/RENT/{first}LANDLORD", round(monthly_credit * 0.30), 0.0))
        txns.append((f"26-{m}", "UPI/GROCERY/BIGBAZAAR", round(monthly_credit * 0.12), 0.0))
        txns.append((f"28-{m}", f"SALARY CREDIT {first}", 0.0, float(monthly_credit)))
    if duplicate_row and months:
        txns.append((f"28-{months[0]}", f"SALARY CREDIT {first}", 0.0, float(monthly_credit)))
    # target a middle salary row for the fraud edit
    salary_rows = [i for i, t in enumerate(txns) if t[3] > 0]
    target_row = salary_rows[len(salary_rows) // 2] if salary_rows else -1

    # account summary
    y += 6
    total_cr = sum(t[3] for t in txns)
    total_dr = sum(t[2] for t in txns)
    closing = opening + total_cr - total_dr
    sx = [ML, ML + 128, ML + 256, ML + 384, MR]
    summ = [("Opening Balance", opening), ("Total Credits", total_cr),
            ("Total Debits", total_dr), ("Closing Balance", closing)]
    for i, (k, v) in enumerate(summ):
        _cell(page, fitz.Rect(sx[i], y, sx[i + 1], y + 13), k, size=7.5, bold=True, align=1)
    y += 13
    for i, (k, v) in enumerate(summ):
        _cell(page, fitz.Rect(sx[i], y, sx[i + 1], y + 14))
        _money_field(page, sx[i] + 6, y + 9.5, v, size=8)
    y += 14 + 8

    # transaction table
    cx = [ML, ML + 55, ML + 270, ML + 355, ML + 440, MR]   # Date|Narration|Debit|Credit|Balance
    hdr = ["Date", "Narration", "Debit", "Credit", "Balance"]
    rh = 13.0
    for i, h in enumerate(hdr):
        _cell(page, fitz.Rect(cx[i], y, cx[i + 1], y + rh), h, size=7.5, bold=True,
              align=(0 if i < 2 else 2))
    y += rh
    bal = float(opening)
    balance_cells: list[dict] = []
    for ri, (date, narr, dr, cr) in enumerate(txns):
        bal += cr - dr
        _cell(page, fitz.Rect(cx[0], y, cx[1], y + rh), "  " + date, size=7.5)
        _cell(page, fitz.Rect(cx[1], y, cx[2], y + rh), "  " + narr, size=7.5)
        _cell(page, fitz.Rect(cx[2], y, cx[3], y + rh))
        _cell(page, fitz.Rect(cx[3], y, cx[4], y + rh))
        _cell(page, fitz.Rect(cx[4], y, cx[5], y + rh))
        if dr:
            _money_field(page, cx[2] + 4, y + 9, dr, size=7.5)
        if cr:
            is_target = ri == target_row
            _money_field(page, cx[3] + 4, y + 9, cr, size=7.5,
                         fields=fields if is_target else None,
                         name="salary_credit" if is_target else "", fraud="inflate")
        # balance cell — recorded so a tamper can keep the running maths consistent
        bx = cx[4] + 4
        _money_field(page, bx, y + 9, round(bal), size=7.5)
        if fields is not None:
            balance_cells.append({"rect_pts": [round(v, 2) for v in _text_rect(bx, y + 9, _money(round(bal)), FONT_BODY, 7.5)],
                                  "amount": round(bal), "row": ri, "size": 7.5, "font": FONT_BODY})
        y += rh

    if fields is not None:
        fields["closing_balance"] = {
            "rect_pts": balance_cells[-1]["rect_pts"] if balance_cells else [0, 0, 0, 0],
            "value": _money(round(closing)), "amount": round(closing), "font": FONT_BODY, "size": 7.5,
            "fraud": "inflate", "kind": "money",
        }
        fields["_balance_column"] = balance_cells
        if "salary_credit" in fields:
            fields["salary_credit"]["row"] = target_row

    meta.title = "Bank Statement"
    apply_metadata(doc, meta)
    return doc


# Larger issuer pools for the layout-family builders (image dataset).
_BANKS2: list[dict] = _BANKS + [
    {"name": "Axis Bank Ltd.", "ifsc": "UTIB0001234", "branch": "Banjara Hills, Hyderabad"},
    {"name": "Kotak Mahindra Bank", "ifsc": "KKBK0005678", "branch": "FC Road, Pune"},
    {"name": "Punjab National Bank", "ifsc": "PUNB0090123", "branch": "Sector 17, Chandigarh"},
    {"name": "Bank of Baroda", "ifsc": "BARB0VJMUMB", "branch": "Ashram Road, Ahmedabad"},
    {"name": "Canara Bank", "ifsc": "CNRB0001111", "branch": "MG Road, Bengaluru"},
]
_DESIGNATIONS = ["Senior Engineer", "Project Manager", "Analyst", "Consultant", "Team Lead",
                 "Associate", "Architect", "Manager - Ops", "Sr. Developer", "Specialist"]


def build_bank_statement_v2(name: str, account_number: str, monthly_credit: float, months: list[str],
                            meta: DocMeta, *, fields: Optional[dict] = None, rng=None) -> "fitz.Document":
    """Layout-FAMILY bank statement: **variable transaction-row count (10-40)**, randomized column widths,
    optional running-balance column, varied bank header/date format. Records many editable money fields
    (every salary credit + several debits + balance cells + closing balance)."""
    import numpy as _np
    rng = rng if rng is not None else _np.random.default_rng()
    doc, page = _new_doc()
    ML, MR = 40.0, PAGE_W - 40.0
    band = _rng_choice(rng, _BANDS); band_fill = band or (0.85, 0.85, 0.85)
    band_txt = (1, 1, 1) if band else (0.1, 0.1, 0.1)
    bank = _rng_choice(rng, _BANKS2)
    bs = float(round(rng.uniform(7.0, 8.0), 1))
    rh = float(round(rng.uniform(12.0, 15.0), 1))
    has_balance = bool(rng.integers(0, 2))
    masked = account_number[:2] + "XXXX" + account_number[-4:]
    first = name.split()[0].upper()

    page.draw_rect(fitz.Rect(ML, 40, MR, 72), color=band_fill, fill=band_fill)
    _htext(page, ML + 8, MR, 56, bank["name"], size=13, bold=True, color=band_txt)
    _htext(page, ML + 8, MR, 67, f"Branch: {bank['branch']}    IFSC: {bank['ifsc']}", size=7.5,
           color=(band_txt[0], band_txt[1], band_txt[2]) if band else (0.3, 0.3, 0.3))
    _htext(page, ML, MR, 90, _rng_choice(rng, ["Statement of Account", "Account Statement", "Bank Statement"]),
           size=10, bold=True, align=1)

    y = 100.0
    for k, v in [("Account Holder", name), ("Account Number", masked),
                 ("Account Type", _rng_choice(rng, ["Savings", "Salary", "Current"])),
                 ("Statement Period", f"{months[0]} - {months[-1]} 2024")]:
        page.insert_text((ML, y), f"{k}:", fontname=FONT_BOLD, fontsize=bs)
        page.insert_text((ML + 110, y), v, fontname=FONT_BODY, fontsize=bs)
        y += 13

    # build a variable-length transaction list (10-40 rows)
    opening = round(monthly_credit * rng.uniform(1.1, 1.8))
    txns: list[tuple] = []
    extra_debits = ["UPI/GROCERY/BIGBAZAAR", "UPI/SWIGGY", "ATM/CASH WDL", "NEFT/CARD/HDFC",
                    "UPI/AMAZON", "POS/RELIANCE", "UPI/ELECTRICITY", "IMPS/TRANSFER"]
    for m in months:
        txns.append((f"03-{m}", f"NEFT/RENT/{first}LANDLORD", round(monthly_credit * 0.30), 0.0))
        for _ in range(int(rng.integers(1, 5))):
            txns.append((f"{int(rng.integers(5,27)):02d}-{m}", _rng_choice(rng, extra_debits),
                         round(monthly_credit * rng.uniform(0.03, 0.18)), 0.0))
        txns.append((f"28-{m}", f"SALARY CREDIT {first}", 0.0, float(monthly_credit)))
    txns = txns[:40]
    salary_rows = [i for i, t in enumerate(txns) if t[3] > 0]
    target_row = salary_rows[len(salary_rows) // 2] if salary_rows else -1

    y += 6
    total_cr = sum(t[3] for t in txns); total_dr = sum(t[2] for t in txns)
    closing = opening + total_cr - total_dr
    sx = [ML, ML + 128, ML + 256, ML + 384, MR]
    for i, (k, v) in enumerate([("Opening Balance", opening), ("Total Credits", total_cr),
                                ("Total Debits", total_dr), ("Closing Balance", closing)]):
        _cell(page, fitz.Rect(sx[i], y, sx[i + 1], y + 13), k, size=7.5, bold=True, align=1)
    y += 13
    for i, (k, v) in enumerate([("Opening Balance", opening), ("Total Credits", total_cr),
                                ("Total Debits", total_dr), ("Closing Balance", closing)]):
        _cell(page, fitz.Rect(sx[i], y, sx[i + 1], y + 14))
        _money_field(page, sx[i] + 6, y + 9.5, v, size=bs,
                     fields=fields if k == "Opening Balance" else None,
                     name="opening_balance" if k == "Opening Balance" else "", fraud="inflate")
    y += 14 + 8

    # transaction table — randomized column widths
    narr_w = rng.uniform(200, 240)
    if has_balance:
        cx = [ML, ML + 55, ML + 55 + narr_w, ML + 55 + narr_w + 70, ML + 55 + narr_w + 145, MR]
        hdr = ["Date", "Narration", "Debit", "Credit", "Balance"]
    else:
        cx = [ML, ML + 55, ML + 55 + narr_w + 60, (ML + 55 + narr_w + 60 + MR) / 2, MR, MR]
        hdr = ["Date", "Narration", "Debit", "Credit"]
    ncol = len(hdr)
    for i in range(ncol):
        _cell(page, fitz.Rect(cx[i], y, cx[i + 1], y + rh), hdr[i], size=7.5, bold=True, align=(0 if i < 2 else 2))
    y += rh
    bal = float(opening)
    balance_cells: list[dict] = []
    for ri, (date, narr, dr, cr) in enumerate(txns):
        if y > PAGE_H - 40:
            break
        bal += cr - dr
        for k in range(ncol):
            _cell(page, fitz.Rect(cx[k], y, cx[k + 1], y + rh))
        page.insert_text((cx[0] + 3, y + rh * 0.62), date, fontname=FONT_BODY, fontsize=7.0)
        page.insert_text((cx[1] + 3, y + rh * 0.62), narr[:46], fontname=FONT_BODY, fontsize=7.0)
        if dr:
            _money_field(page, cx[2] + 4, y + rh * 0.62, dr, size=7.0,
                         fields=fields if (ri % 5 == 0) else None,
                         name=f"debit_{ri}" if (ri % 5 == 0) else "", fraud="inflate")
        if cr:
            is_t = ri == target_row
            _money_field(page, cx[3] + 4, y + rh * 0.62, cr, size=7.0,
                         fields=fields if is_t else None,
                         name="salary_credit" if is_t else f"credit_{ri}", fraud="inflate")
            if not is_t:   # still record other salary rows as editable
                _record_field(fields, f"credit_{ri}", cx[3] + 4, y + rh * 0.62, _money(round(cr)),
                              font=FONT_BODY, size=7.0, fraud="inflate", kind="money", amount=round(cr))
        if has_balance:
            bx = cx[4] + 4
            _money_field(page, bx, y + rh * 0.62, round(bal), size=7.0)
            if fields is not None:
                balance_cells.append({"rect_pts": [round(v, 2) for v in _text_rect(bx, y + rh * 0.62, _money(round(bal)), FONT_BODY, 7.0)],
                                      "amount": round(bal), "row": ri, "size": 7.0, "font": FONT_BODY})
        y += rh

    if fields is not None:
        if has_balance and balance_cells:
            fields["closing_balance"] = {"rect_pts": balance_cells[-1]["rect_pts"],
                                         "value": _money(round(closing)), "amount": round(closing),
                                         "font": FONT_BODY, "size": 7.0, "fraud": "inflate", "kind": "money"}
            fields["_balance_column"] = balance_cells
        if "salary_credit" in fields:
            fields["salary_credit"]["row"] = target_row
    meta.title = "Bank Statement"
    apply_metadata(doc, meta)
    return doc


def build_salary_slip_v2(name: str, employer: str, month: str, net_monthly: float, meta: DocMeta,
                         *, fields: Optional[dict] = None, rng=None) -> "fitz.Document":
    """Layout-FAMILY payslip: **variable earning/deduction line counts**, table vs banded styles, varied
    headers/fonts. Records many editable money fields (basic, gross, net_pay + several line items)."""
    import numpy as _np
    rng = rng if rng is not None else _np.random.default_rng()
    doc, page = _new_doc()
    ML, MR = 40.0, PAGE_W - 40.0
    midx = (ML + MR) / 2
    band = _rng_choice(rng, _BANDS); band_fill = band or (0.85, 0.85, 0.85)
    band_txt = (1, 1, 1) if band else (0.1, 0.1, 0.1)
    addr = _rng_choice(rng, [t["addr"] for t in _F16_TEMPLATES])
    bs = float(round(rng.uniform(8.0, 9.0), 1))
    rh = float(round(rng.uniform(14.0, 16.0), 1))
    net = float(net_monthly)
    gross = round(net / rng.uniform(0.82, 0.88))
    basic = round(gross * rng.uniform(0.40, 0.52))
    hra = round(basic * 0.5)
    conveyance = _rng_choice(rng, [1600, 1800, 2400])
    # variable number of extra allowances
    extra_allow = [("Special Allowance", None), ("Medical Allowance", 1250), ("LTA", round(basic * 0.08)),
                   ("Performance Bonus", round(gross * 0.05)), ("Food Coupons", 2200)]
    n_allow = int(rng.integers(1, 4))
    chosen_allow = [extra_allow[i] for i in sorted(rng.permutation(len(extra_allow))[:n_allow])]
    epf = round(basic * 0.12); prof_tax = _rng_choice(rng, [200, 150, 0])
    ded_total = gross - round(net)
    tds = max(0, ded_total - epf - prof_tax)

    page.draw_rect(fitz.Rect(ML, 40, MR, 72), color=band_fill, fill=band_fill)
    _htext(page, ML + 8, MR, 56, employer, size=12, bold=True, color=band_txt)
    _htext(page, ML + 8, MR, 67, addr[0] + ",  " + addr[1], size=7.5,
           color=(0.9, 0.9, 0.9) if band else (0.3, 0.3, 0.3))
    _htext(page, ML, MR, 90, f"Payslip for the month of {month}", size=10, bold=True, align=1)

    y = 102.0
    left = [("Employee Name", name), ("Employee ID", _emp_id(name)), ("Designation", _rng_choice(rng, _DESIGNATIONS))]
    right = [("Date of Joining", "01-Jul-2019"), ("Pay Period", month), ("Days Paid", "30 / 30")]
    for (ll, lv), (rl, rv) in zip(left, right):
        page.insert_text((ML, y), f"{ll}:", fontname=FONT_BOLD, fontsize=bs)
        page.insert_text((ML + 95, y), lv, fontname=FONT_BODY, fontsize=bs)
        page.insert_text((midx + 10, y), f"{rl}:", fontname=FONT_BOLD, fontsize=bs)
        page.insert_text((midx + 90, y), rv, fontname=FONT_BODY, fontsize=bs)
        y += 15
    y += 6

    e_amt, d_amt = midx - 80, MR - 80
    _cell(page, fitz.Rect(ML, y, e_amt, y + rh), "  Earnings", size=bs, bold=True)
    _cell(page, fitz.Rect(e_amt, y, midx, y + rh), "Amount  ", size=bs, bold=True, align=2)
    _cell(page, fitz.Rect(midx, y, d_amt, y + rh), "  Deductions", size=bs, bold=True)
    _cell(page, fitz.Rect(d_amt, y, MR, y + rh), "Amount  ", size=bs, bold=True, align=2)
    y += rh
    earn = [("Basic", basic, "basic", "inflate"), ("House Rent Allowance", hra, "hra", "inflate"),
            ("Conveyance Allowance", conveyance, "", "none")]
    acc = basic + hra + conveyance
    for label, amt in chosen_allow:
        amt = amt if amt is not None else max(1000, gross - acc - 1)
        earn.append((label, amt, f"earn_{label.split()[0].lower()}", "inflate")); acc += amt
    ded = [("Provident Fund (EPF)", epf), ("Professional Tax", prof_tax), ("Income Tax (TDS)", tds)]
    nrows = max(len(earn), len(ded))
    for i in range(nrows):
        if i < len(earn):
            el, ev, efn, efr = earn[i]
            _cell(page, fitz.Rect(ML, y, e_amt, y + rh), "  " + el, size=bs)
            _cell(page, fitz.Rect(e_amt, y, midx, y + rh))
            _money_field(page, e_amt + 6, y + rh * 0.66, ev, size=bs, fields=fields if efn else None, name=efn, fraud=efr)
        else:
            _cell(page, fitz.Rect(ML, y, e_amt, y + rh)); _cell(page, fitz.Rect(e_amt, y, midx, y + rh))
        if i < len(ded):
            dl, dv = ded[i]
            _cell(page, fitz.Rect(midx, y, d_amt, y + rh), "  " + dl, size=bs)
            _cell(page, fitz.Rect(d_amt, y, MR, y + rh))
            _money_field(page, d_amt + 6, y + rh * 0.66, dv, size=bs,
                         fields=fields if dl.startswith("Income") else None,
                         name="tds" if dl.startswith("Income") else "", fraud="inflate")
        else:
            _cell(page, fitz.Rect(midx, y, d_amt, y + rh)); _cell(page, fitz.Rect(d_amt, y, MR, y + rh))
        y += rh
    _cell(page, fitz.Rect(ML, y, e_amt, y + rh), "  Gross Earnings", size=bs, bold=True)
    _cell(page, fitz.Rect(e_amt, y, midx, y + rh))
    _money_field(page, e_amt + 6, y + rh * 0.66, gross, size=bs, font=FONT_BOLD, fields=fields, name="gross", fraud="inflate")
    _cell(page, fitz.Rect(midx, y, d_amt, y + rh), "  Total Deductions", size=bs, bold=True)
    _cell(page, fitz.Rect(d_amt, y, MR, y + rh))
    _money_field(page, d_amt + 6, y + rh * 0.66, ded_total, size=bs, font=FONT_BOLD)
    y += rh + 8

    page.draw_rect(fitz.Rect(ML, y, MR, y + 20), color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93))
    page.insert_text((ML + 6, y + 14), "Net Pay (take-home)", fontname=FONT_BOLD, fontsize=11)
    _money_field(page, MR - 130, y + 14, net, size=11, font=FONT_BOLD, fields=fields, name="net_pay", fraud="inflate")
    meta.title = "Salary Slip"
    apply_metadata(doc, meta)
    return doc


def build_identity_v2(name: str, pan: str, dob: str, meta: DocMeta, *, fields: Optional[dict] = None,
                      father: str = "", rng=None) -> "fitz.Document":
    """PAN card with a couple of layout styles (field order / fonts / optional photo box)."""
    import numpy as _np
    rng = rng if rng is not None else _np.random.default_rng()
    doc, page = _new_doc()
    y = _header(page, "INCOME TAX DEPARTMENT", _rng_choice(rng, ["Permanent Account Number Card",
                "Income Tax PAN Services", "Permanent Account Number"]))
    if bool(rng.integers(0, 2)):
        page.draw_rect(fitz.Rect(MR_ := PAGE_W - 150, 110, PAGE_W - 60, 200), color=(0.6, 0.6, 0.6), width=0.8)
        _htext(page, MR_, PAGE_W - 60, 158, "PHOTO", size=8, align=1, color=(0.6, 0.6, 0.6))
    base = [("Name", name, "name", "swap", FONT_BODY, 12, "text"),
            ("Father's Name", father or "Kumar " + name.split()[-1], "", "none", FONT_BODY, 12, "text"),
            ("Date of Birth", dob, "dob", "swap", FONT_BODY, 12, "date"),
            ("Permanent Account No.", pan, "pan", "swap", FONT_BOLD, 13, "pan")]
    if bool(rng.integers(0, 2)):
        base[2], base[3] = base[3], base[2]   # vary field order
    _id_rows(page, y + 24, base, fields, leading=float(rng.uniform(28, 34)))
    meta.title = "PAN Card"; apply_metadata(doc, meta)
    return doc


def build_aadhaar_v2(name: str, aadhaar: str, dob: str, gender: str, address: list[str], meta: DocMeta,
                     *, fields: Optional[dict] = None, rng=None) -> "fitz.Document":
    """Aadhaar (doc-style, SYNTHETIC) with light layout variety."""
    import numpy as _np
    rng = rng if rng is not None else _np.random.default_rng()
    doc, page = _new_doc()
    y = _header(page, "GOVERNMENT OF INDIA", "Unique Identification Authority of India (UIDAI)")
    page.insert_textbox(fitz.Rect(110, 300, 490, 400), "SPECIMEN", fontname=FONT_BOLD, fontsize=72,
                        color=(0.93, 0.93, 0.93), align=1)
    rows = [("Name", name, "name", "swap", FONT_BODY, 12, "text"),
            ("Date of Birth", dob, "dob", "swap", FONT_BODY, 12, "date"),
            ("Gender", gender, "", "none", FONT_BODY, 12, "text"),
            ("Aadhaar No.", aadhaar, "aadhaar_number", "swap", FONT_BOLD, float(rng.uniform(13, 15)), "aadhaar")]
    y = _id_rows(page, y + 24, rows, fields, leading=float(rng.uniform(28, 33)))
    page.insert_text((MARGIN_X, y), "Address:", fontname=FONT_BODY, fontsize=11, color=(0.25, 0.25, 0.25))
    _lines(page, y + 16, address, x=MARGIN_X + 16, leading=16, size=10)
    page.insert_textbox(fitz.Rect(MARGIN_X, PAGE_H - 70, PAGE_W - MARGIN_X, PAGE_H - 50),
                        "Synthetic specimen generated for tamper-detection research - not a real Aadhaar.",
                        fontname=FONT_BODY, fontsize=8, color=(0.5, 0.5, 0.5), align=1)
    meta.title = "Aadhaar"; apply_metadata(doc, meta)
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
