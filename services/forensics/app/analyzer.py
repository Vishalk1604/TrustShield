"""Forensic document analysis engine — Phase 1.

Analyzes a single PDF and returns a list of EvidenceItems (forensic category) plus a structural
template fingerprint used by the cross-application graph in Phase 5.

All analysis is pure local file I/O: no network, no external services.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from shared.schemas import EvidenceCategory, EvidenceItem, Severity

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# Substrings (lowercase) in producer/creator that indicate editing-tool origin.
_SUSPICIOUS_PRODUCER_KEYWORDS = [
    "photoshop",
    "ilovepdf",
    "pdfescape",
    "foxit",
    "inkscape",
    "gimp",
    "affinity",
    "scribus",
    "pixelmator",
]

# Body-text font name fragments. Anything outside the expected body set in a body-size span is suspect.
_EXPECTED_BODY_FONTS = {"helv", "hebo", "cour", "timesroman", "courier", "helvetica"}

# Serif fonts that would be unexpected in a sans-serif document.
_SERIF_FONTS = {"tiro", "georgia", "times", "timesroman", "palatino", "garamond", "cambria"}

# Minimum gap (days) between creation and modification before we flag "suspicious late edit".
_MOD_GAP_DAYS = 30

# Maximum allowable future-date drift (days): creation date this far in the future is suspicious.
_FUTURE_DAYS = 30


# --------------------------------------------------------------------------
# Date parsing
# --------------------------------------------------------------------------

def _parse_pdf_date(date_str: str) -> Optional[datetime]:
    """Parse PDF date string D:YYYYMMDDHHmmSS+TZ -> datetime (UTC). Returns None on failure."""
    if not date_str:
        return None
    s = date_str.strip()
    if s.startswith("D:"):
        s = s[2:]
    m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            tzinfo=timezone.utc,
        )
    except (ValueError, OverflowError):
        return None


# --------------------------------------------------------------------------
# Main analyzer
# --------------------------------------------------------------------------

class DocumentAnalyzer:
    """Analyze a single PDF for forensic tamper signals.

    Usage:
        result = DocumentAnalyzer(path, doc_type="form16").analyze()
    """

    def __init__(self, path: str, doc_type: str = "other", filename: Optional[str] = None):
        self.path = path
        self.doc_type = doc_type
        self.filename = filename or Path(path).name
        self._raw: bytes = Path(path).read_bytes()
        self._doc: fitz.Document = fitz.open(stream=self._raw, filetype="pdf")

    def close(self) -> None:
        if not self._doc.is_closed:
            self._doc.close()

    def __enter__(self) -> "DocumentAnalyzer":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def analyze(self, enable_reocr: bool = True) -> dict:
        """Run all forensic checks and return the result dict.

        ``enable_reocr`` toggles the OCR-based re-OCR cross-check (§6.D2). It is left on
        for the evidence path but switched off for the learned-model feature path (which
        excludes the re-OCR signal anyway), so scoring does not pay the OCR cost twice.
        """
        findings: list[EvidenceItem] = []
        findings.extend(self._check_metadata())
        findings.extend(self._check_whitebox_edits())
        findings.extend(self._check_font_inconsistency())
        findings.extend(self._check_duplicate_images())
        findings.extend(self._check_incremental_updates())
        if enable_reocr:
            findings.extend(self._check_reocr_mismatch())

        return {
            "filename": self.filename,
            "doc_type": self.doc_type,
            "page_count": self._doc.page_count,
            "template_fingerprint": self._compute_template_fingerprint(),
            "findings": [_ev_to_dict(f) for f in findings],
        }

    # ------------------------------------------------------------------
    # Check: PDF metadata
    # ------------------------------------------------------------------

    def _check_metadata(self) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        meta = self._doc.metadata or {}
        producer: str = (meta.get("producer") or "").strip()
        creator: str = (meta.get("creator") or "").strip()
        creation_str: str = meta.get("creationDate") or ""
        mod_str: str = meta.get("modDate") or ""

        p_low = producer.lower()
        c_low = creator.lower()

        # 1. Suspicious editing tool in producer/creator.
        for kw in _SUSPICIOUS_PRODUCER_KEYWORDS:
            if kw in p_low or kw in c_low:
                items.append(EvidenceItem(
                    category=EvidenceCategory.FORENSIC,
                    severity=Severity.HIGH,
                    title="Suspicious producer software detected",
                    description=(
                        f"'{self.filename}' was produced/modified by '{producer or creator}', "
                        "a known image/PDF editing tool rather than a document-issuing system. "
                        "Legitimate bank or income documents are not produced by photo editors."
                    ),
                    source_location="PDF metadata / producer field",
                    values={"producer": producer, "creator": creator},
                    confidence=0.90,
                ))
                break  # one finding per document is enough for this signal

        # 2. Parse creation and modification dates.
        created = _parse_pdf_date(creation_str)
        modified = _parse_pdf_date(mod_str)
        now = datetime.now(timezone.utc)

        if created and modified:
            gap_days = (modified - created).days
            if gap_days > _MOD_GAP_DAYS:
                items.append(EvidenceItem(
                    category=EvidenceCategory.FORENSIC,
                    severity=Severity.MEDIUM,
                    title="Document modified long after creation",
                    description=(
                        f"'{self.filename}' was created on {created.date()} but its modification "
                        f"date is {modified.date()} — a gap of {gap_days} days. "
                        "Legitimate statements are typically issued with matching creation/mod dates."
                    ),
                    source_location="PDF metadata / modDate vs creationDate",
                    values={"creation_date": str(created.date()), "mod_date": str(modified.date()),
                            "gap_days": gap_days},
                    confidence=0.80,
                ))

            if gap_days < 0:
                items.append(EvidenceItem(
                    category=EvidenceCategory.FORENSIC,
                    severity=Severity.HIGH,
                    title="Impossible date ordering: modification before creation",
                    description=(
                        f"'{self.filename}' records a modification date ({modified.date()}) "
                        f"that precedes its creation date ({created.date()}) — "
                        "this is impossible and indicates manipulated metadata."
                    ),
                    source_location="PDF metadata / modDate vs creationDate",
                    values={"creation_date": str(created.date()), "mod_date": str(modified.date()),
                            "gap_days": gap_days},
                    confidence=0.98,
                ))

        if created and (created - now).days > _FUTURE_DAYS:
            items.append(EvidenceItem(
                category=EvidenceCategory.FORENSIC,
                severity=Severity.HIGH,
                title="Document creation date is in the future",
                description=(
                    f"'{self.filename}' records a creation date of {created.date()}, which is "
                    f"{(created - now).days} days in the future relative to today. "
                    "This indicates fabricated metadata."
                ),
                source_location="PDF metadata / creationDate",
                values={"creation_date": str(created.date()), "today": str(now.date()),
                        "days_in_future": (created - now).days},
                confidence=0.98,
            ))

        return items

    # ------------------------------------------------------------------
    # Check: white-box edits (white rect drawn over text)
    # ------------------------------------------------------------------

    def _check_whitebox_edits(self) -> list[EvidenceItem]:
        """Detect white-filled rectangles drawn over existing text content.

        The tamper technique: draw a white box over a value, then insert new text. The original
        value remains in the content stream (recoverable); the white rect + new span is detectable.
        """
        items: list[EvidenceItem] = []
        for page_num, page in enumerate(self._doc):
            # Get all drawing paths on this page.
            paths = page.get_drawings()
            white_rects = [
                p["rect"]
                for p in paths
                if p.get("fill") in ((1, 1, 1), (1.0, 1.0, 1.0))
                and p.get("rect") is not None
            ]
            if not white_rects:
                continue

            # Get all text blocks to check for overlap.
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            text_rects = []
            for b in blocks:
                if b.get("type") == 0:  # text block
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            span_rect = fitz.Rect(span["bbox"])
                            if span["text"].strip():
                                text_rects.append(span_rect)

            # Check if any white rect substantially overlaps a text span.
            overlapping = []
            for wr in white_rects:
                wr_fitz = fitz.Rect(wr)
                for tr in text_rects:
                    if not wr_fitz.intersects(tr):
                        continue
                    inter = wr_fitz & tr
                    if inter.is_empty:
                        continue
                    # Overlap fraction relative to the text span.
                    overlap_frac = (inter.width * inter.height) / max(
                        tr.width * tr.height, 1e-6
                    )
                    if overlap_frac > 0.30:  # >30% of the text span is covered
                        overlapping.append(wr_fitz)
                        break

            if overlapping:
                regions = [
                    {"page": page_num + 1, "bbox": _round_bbox(wr)}
                    for wr in overlapping
                ]
                items.append(EvidenceItem(
                    category=EvidenceCategory.FORENSIC,
                    severity=Severity.HIGH,
                    title="White-box edit detected (covered text)",
                    description=(
                        f"'{self.filename}' page {page_num + 1} contains {len(overlapping)} "
                        "white-filled rectangle(s) drawn over existing text content. "
                        "This is a classic 'whiteout' technique: the original value is hidden "
                        "visually but survives in the PDF content stream."
                    ),
                    source_location=f"page {page_num + 1} — drawing objects vs text layer",
                    values={"page": page_num + 1, "whitebox_count": len(overlapping),
                            "regions": regions},
                    confidence=0.88,
                ))
        return items

    # ------------------------------------------------------------------
    # Check: font inconsistency
    # ------------------------------------------------------------------

    def _check_font_inconsistency(self) -> list[EvidenceItem]:
        """Detect mixed fonts at body-text size that suggest a copied/pasted or edited span.

        Legitimate documents produced by a single issuing system use one body font throughout.
        Edited figures inserted after the fact often use a different (serif) font.
        """
        items: list[EvidenceItem] = []
        for page_num, page in enumerate(self._doc):
            # Collect font usage at body size (8–16pt) — skip tiny annotations/footers.
            font_sizes: dict[str, list[float]] = {}  # font_basename -> list of sizes
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            for b in blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        sz = span.get("size", 0)
                        if sz < 8 or sz > 20:  # skip headers/tiny text
                            continue
                        font = (span.get("font") or "").lower()
                        base = _font_base(font)
                        font_sizes.setdefault(base, []).append(sz)

            if len(font_sizes) < 2:
                continue  # only one font family — no inconsistency

            # Find the dominant font (by span count).
            dominant = max(font_sizes, key=lambda f: len(font_sizes[f]))
            minority_fonts = {f for f in font_sizes if f != dominant}

            # Flag if any minority font is a known serif when dominant is sans-serif,
            # OR if any unexpected font appears in body text.
            dom_is_sans = _is_sans(dominant)
            suspects = []
            for mf in minority_fonts:
                if dom_is_sans and _is_serif(mf):
                    suspects.append(mf)
                elif mf not in _EXPECTED_BODY_FONTS and not mf.startswith(dominant[:4]):
                    suspects.append(mf)

            if suspects:
                items.append(EvidenceItem(
                    category=EvidenceCategory.FORENSIC,
                    severity=Severity.HIGH,
                    title="Font inconsistency in body text",
                    description=(
                        f"'{self.filename}' page {page_num + 1} uses '{dominant}' as the body font "
                        f"but also contains text spans in {suspects}. "
                        "Edited figures inserted post-production often introduce a different font."
                    ),
                    source_location=f"page {page_num + 1} — text spans",
                    values={"dominant_font": dominant, "suspect_fonts": suspects,
                            "all_fonts": list(font_sizes.keys())},
                    confidence=0.85,
                ))
        return items

    # ------------------------------------------------------------------
    # Check: duplicate images (copy-paste)
    # ------------------------------------------------------------------

    def _check_duplicate_images(self) -> list[EvidenceItem]:
        """Detect identical image objects appearing multiple times (copy-paste signal)."""
        items: list[EvidenceItem] = []
        seen: dict[bytes, list[int]] = {}  # image_hash -> list of xrefs where seen
        for page_num, page in enumerate(self._doc):
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    img_data = self._doc.extract_image(xref)
                    content = img_data.get("image") or b""
                    if not content:
                        continue
                    digest = hashlib.sha256(content).digest()
                    seen.setdefault(digest, []).append(xref)
                except Exception:
                    continue

        duplicated = {d: refs for d, refs in seen.items() if len(set(refs)) > 1 or
                      # same image inserted on two positions (xref may repeat)
                      len(refs) > len(set(refs))}

        # Also check page-level: same xref on same page = inserted twice
        page_images: dict[int, list[int]] = {}
        for page_num, page in enumerate(self._doc):
            xrefs = [img[0] for img in page.get_images(full=True)]
            if len(xrefs) != len(set(xrefs)):
                page_images[page_num] = xrefs

        all_dup = bool(duplicated) or bool(page_images)

        if all_dup:
            details: list[str] = []
            for pn, xrefs in page_images.items():
                dupes = [x for x in set(xrefs) if xrefs.count(x) > 1]
                details.append(f"page {pn + 1}: xrefs {dupes} appear >1 time")

            items.append(EvidenceItem(
                category=EvidenceCategory.FORENSIC,
                severity=Severity.MEDIUM,
                title="Duplicate image objects detected (copy-paste signal)",
                description=(
                    f"'{self.filename}' contains identical image content inserted more than once. "
                    "A verbatim-duplicate seal, stamp, or graphic is a copy-paste artefact "
                    "indicating the document was assembled from pasted components."
                ),
                source_location="PDF image objects",
                values={"duplicate_details": details or ["image bytes duplicated across xrefs"]},
                confidence=0.80,
            ))
        return items

    # ------------------------------------------------------------------
    # Check: incremental updates (multiple %%EOF)
    # ------------------------------------------------------------------

    def _check_incremental_updates(self) -> list[EvidenceItem]:
        """Detect incremental-update saves: a legitimate document has exactly one %%EOF.

        An incremental save (as used in `tamper.incremental_overlay`) appends a new cross-reference
        section and a second %%EOF without rewriting the original content. This leaves an audit
        trail but also reveals a post-hoc revision.
        """
        items: list[EvidenceItem] = []
        eof_count = self._raw.count(b"%%EOF")
        if eof_count > 1:
            items.append(EvidenceItem(
                category=EvidenceCategory.FORENSIC,
                severity=Severity.MEDIUM,
                title="Incremental update detected (post-hoc revision)",
                description=(
                    f"'{self.filename}' contains {eof_count} PDF end-of-file markers. "
                    "A legitimate document has exactly one. Multiple markers indicate the file "
                    "was saved incrementally after initial creation — a revision was appended "
                    "rather than producing a fresh document."
                ),
                source_location="PDF raw bytes — %%EOF count",
                values={"eof_count": eof_count},
                confidence=0.92,
            ))
        return items

    # ------------------------------------------------------------------
    # Check: re-OCR vs text-layer cross-check (roadmap §6.D2)
    # ------------------------------------------------------------------

    def _check_reocr_mismatch(self) -> list[EvidenceItem]:
        """Render each page, OCR it, and compare the *visible* values against the
        embedded text layer.

        A "whiteout" edit hides the original value behind a white box and draws the
        forged value on top: the original survives in the text layer but is not visible
        on the page. Rendering + OCR sees only the visible (forged) value, so a value
        present in the text layer is missing from the rendered page — the mismatch.

        This signal is layout-independent and would survive flattening/re-scanning that
        defeats PDF-structure checks. It compares only OCR-robust tokens (money amounts
        and PANs) with fuzzy matching, so legitimate documents (where every value is
        both in the layer and visible) produce no findings.

        Degrades gracefully: returns [] if Tesseract is unavailable or OCR is empty.
        """
        from services.forensics.app.ocr import ocr_page, ocr_region, tesseract_available

        items: list[EvidenceItem] = []
        if not tesseract_available():
            return items

        for page_num, page in enumerate(self._doc):
            embedded = page.get_text("text") or ""
            # 150 DPI is enough to read amounts/PANs and is faster than the 200 DPI used for
            # full extraction — detection results are identical on the synthetic corpus.
            visible = ocr_page(page, dpi=150) or ""
            # Require a substantial OCR result so a "missing" value means genuinely hidden,
            # not a wholesale OCR failure on a blank/image page.
            if len(visible.strip()) < 40:
                continue

            for kind, label in (("money", "monetary amount"), ("pan", "PAN")):
                emb = _sensitive_tokens(embedded, kind)   # {normalized: literal}
                if not emb:
                    continue
                # Visibility set = what the rendered page actually shows. For money we use
                # ALL digit runs (a whiteboxed amount is absent entirely; a rendered amount
                # shows up even if OCR drops its "Rs." prefix). For PAN, the PAN tokens.
                if kind == "money":
                    ocr_tokens = _digit_runs(visible)
                else:
                    ocr_tokens = set(_sensitive_tokens(visible, "pan").keys())
                emb_norms = set(emb)
                candidates = {n for n in emb if not _is_visible(n, ocr_tokens, emb_norms)}
                # Spatial confirmation: a value only counts as HIDDEN if a high-DPI crop of its OWN
                # bbox does not show it. On a dense page (a real Form 16 has ~16 table amounts) full-page
                # OCR can drop a small number, and a different-but-close value elsewhere then "explains it
                # away" — a false positive. The crop settles it: a genuine whiteout shows a different value
                # (or blank) at that location, while a merely-mis-OCR'd value is plainly rendered there.
                hidden_rects: dict[str, "fitz.Rect"] = {}
                for n in candidates:
                    try:
                        rects = page.search_for(emb[n])
                    except Exception:
                        rects = []
                    if not rects:
                        continue  # can't locate the text-layer value → conservative: don't flag
                    rect = rects[0]
                    region_txt = ocr_region(page, rect)
                    region_tokens = _digit_runs(region_txt) | set(_sensitive_tokens(region_txt, "pan").keys())
                    if any(_edit_distance_le1(n, t) for t in region_tokens):
                        continue  # the value IS rendered at its own location → OCR miss, not hidden
                    hidden_rects[n] = rect
                if not hidden_rects:
                    continue
                visible_literals = sorted({emb[x] for x in emb if x not in hidden_rects})
                for n, rect in sorted(hidden_rects.items()):
                    literal = emb[n]
                    region = {"page": page_num + 1, "bbox": _round_bbox(rect)}
                    items.append(EvidenceItem(
                        category=EvidenceCategory.FORENSIC,
                        severity=Severity.HIGH,
                        title="Visible content contradicts PDF text layer (re-OCR cross-check)",
                        description=(
                            f"'{self.filename}' page {page_num + 1}: the {label} "
                            f"'{literal}' is present in the PDF text layer but is not "
                            "visible on the rendered page — a hallmark of a covered/overlaid "
                            "edit where the original survives in the content stream while a "
                            "different value (or none) is shown. This check reads pixels "
                            "(OCR), not PDF structure, so it catches edits even when "
                            "structural residue is cleaned or the document is flattened."
                        ),
                        source_location=f"page {page_num + 1} — rendered image vs text layer",
                        values={
                            "page": page_num + 1,
                            "check": "reocr",
                            "kind": kind,
                            "hidden_text_layer_value": literal,
                            "visible_values": visible_literals,
                            "regions": [region],
                        },
                        confidence=0.85,
                    ))
        return items

    # ------------------------------------------------------------------
    # Template fingerprint
    # ------------------------------------------------------------------

    def _compute_template_fingerprint(self) -> str:
        """Structural hash capturing document template identity (not individual data content).

        Captures: PDF producer, font names used (sorted), image count per page, page count.
        Documents built from the same template by the same system get the same fingerprint,
        regardless of the name/PAN/figure substitutions. Used by Phase 5 for cluster detection.
        """
        meta = self._doc.metadata or {}
        producer = (meta.get("producer") or "").strip()

        components: list[str] = [f"producer:{producer}", f"pages:{self._doc.page_count}"]

        for pg_num, page in enumerate(self._doc):
            fonts: set[str] = set()
            blocks = page.get_text("dict").get("blocks", [])
            for b in blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        fn = (span.get("font") or "").lower()
                        if fn:
                            fonts.add(_font_base(fn))
            img_count = len(page.get_images())
            drawing_count = len(page.get_drawings())
            components.append(
                f"p{pg_num}:fonts={','.join(sorted(fonts))};imgs={img_count};draws={drawing_count}"
            )

        fingerprint_input = "|".join(components)
        return hashlib.sha256(fingerprint_input.encode()).hexdigest()[:32]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _font_base(font: str) -> str:
    """Normalise a font name to its base family (strip bold/italic suffixes)."""
    f = font.lower().replace("-", "").replace("_", "").replace(" ", "")
    for suffix in ("bold", "italic", "oblique", "regular", "mt", "ps"):
        if f.endswith(suffix):
            f = f[: -len(suffix)]
    return f.strip()


def _is_serif(font_base: str) -> bool:
    for kw in _SERIF_FONTS:
        if kw in font_base:
            return True
    return False


def _is_sans(font_base: str) -> bool:
    for kw in ("helv", "helvetica", "arial", "calibri", "verdana", "hebo"):
        if kw in font_base:
            return True
    return False


# --- re-OCR cross-check + tamper-localization helpers (§6.D2 / §6.D3) ---

# Only currency-prefixed amounts — bare numbers (PIN codes, dates, survey/ref numbers)
# render inconsistently under OCR (internal spaces, line breaks) and are not what gets
# fraudulently whiteboxed. Requiring "Rs."/"INR"/"₹" keeps the check on real money values.
_MONEY_RE = re.compile(r"(?:Rs\.?|INR|₹)\s*(\d[\d,]*\d)", re.IGNORECASE)
_PAN_RE = re.compile(r"[A-Z]{5}\d{4}[A-Z]")


_DIGIT_RUN_RE = re.compile(r"\d[\d,]*\d")


def _round_bbox(rect: "fitz.Rect") -> list[float]:
    """Round a fitz.Rect to a [x0, y0, x1, y1] list of 1-decimal floats."""
    return [round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1)]


def _digit_runs(text: str) -> set[str]:
    """All comma-free digit runs (≥4 digits) in `text` — used as the OCR visibility set."""
    return {
        m.group(0).replace(",", "")
        for m in _DIGIT_RUN_RE.finditer(text)
        if len(m.group(0).replace(",", "")) >= 4
    }


def _sensitive_tokens(text: str, kind: str) -> dict[str, str]:
    """Extract OCR-robust tokens. Returns {normalized_key: literal_as_found}.

    kind='money' -> digit runs with ≥4 digits (keyed by digits only).
    kind='pan'   -> PAN pattern (keyed by the uppercased token).
    """
    out: dict[str, str] = {}
    if kind == "money":
        for m in _MONEY_RE.finditer(text):
            literal = m.group(1)
            digits = literal.replace(",", "")
            if len(digits) >= 4:
                out.setdefault(digits, literal)
    elif kind == "pan":
        for m in _PAN_RE.finditer(text.upper()):
            out.setdefault(m.group(0), m.group(0))
    return out


def _edit_distance_le1(a: str, b: str) -> bool:
    """True if `a` and `b` differ by at most one insertion/deletion/substitution.

    This tolerates the common OCR slips (a dropped/added/misread digit) so that a value
    which IS rendered but mis-OCR'd is not mistaken for a hidden one.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:  # one substitution
        return sum(c1 != c2 for c1, c2 in zip(a, b)) == 1
    shorter, longer = (a, b) if la < lb else (b, a)
    i = j = 0
    skipped = False
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def _is_visible(value: str, ocr_tokens: set[str], other_values: set[str]) -> bool:
    """Decide whether a text-layer `value` is actually rendered on the page.

    `value` is visible if some OCR token is within one edit of it — UNLESS that OCR
    token exactly equals a *different* real text-layer value. That guard distinguishes:
      • OCR misread: 143,500 rendered but read as 43,500 (43,500 is not its own value)
        → 43,500 explains 143,500 → visible (don't flag).
      • Genuine hide: 1,450,000 covered; the only near token is 145,000, which is the
        real (separate) TDS value → it cannot explain the gross → 1,450,000 stays hidden.
    """
    for tok in ocr_tokens:
        if not _edit_distance_le1(value, tok):
            continue
        if tok != value and tok in other_values:
            continue  # this OCR token is a *different* real value, not a misread of `value`
        return True
    return False


def _first_search_bbox(page: "fitz.Page", literal: str) -> Optional[list[float]]:
    """Best-effort bbox of `literal` on the page via PyMuPDF search. None if not found."""
    try:
        rects = page.search_for(literal)
        if rects:
            return _round_bbox(rects[0])
    except Exception:
        pass
    return None


def render_tamper_overlay(path: str, regions: list[dict], dpi: int = 150) -> bytes:
    """Render the page referenced by `regions` with red boxes over the tamper bboxes.

    Pure PyMuPDF (no Tesseract): draws semi-transparent red rectangles on an in-memory
    copy of the page (never saved) and returns PNG bytes. Returns b'' on failure.
    """
    if not regions:
        return b""
    try:
        page_no = int(regions[0].get("page", 1))
        with fitz.open(path) as doc:
            idx = max(0, min(page_no - 1, doc.page_count - 1))
            page = doc[idx]
            for reg in regions:
                if int(reg.get("page", page_no)) != page_no:
                    continue
                bbox = reg.get("bbox")
                if not bbox:
                    continue
                rect = fitz.Rect(*bbox)
                page.draw_rect(
                    rect, color=(0.9, 0.1, 0.1), fill=(0.9, 0.1, 0.1),
                    fill_opacity=0.22, width=1.5,
                )
            return page.get_pixmap(dpi=dpi).tobytes("png")
    except Exception:
        return b""


def _ev_to_dict(ev: EvidenceItem) -> dict:
    return ev.model_dump(mode="json")


# --------------------------------------------------------------------------
# Convenience function (used by the endpoint and the test suite)
# --------------------------------------------------------------------------

def analyze_pdf(
    path: str,
    doc_type: str = "other",
    filename: Optional[str] = None,
    enable_reocr: bool = True,
) -> dict:
    """Analyze a PDF file at `path` and return the forensics result dict.

    Set ``enable_reocr=False`` to skip the OCR-based re-OCR cross-check (§6.D2) — used by
    the model-feature path, which excludes that signal and so should not pay the OCR cost.

    Returns:
        {
            "filename": str,
            "doc_type": str,
            "page_count": int,
            "template_fingerprint": str,
            "findings": list[dict],  # serialised EvidenceItems
        }
    """
    with DocumentAnalyzer(path, doc_type=doc_type, filename=filename) as da:
        return da.analyze(enable_reocr=enable_reocr)
