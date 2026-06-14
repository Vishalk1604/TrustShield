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

    def analyze(self) -> dict:
        """Run all forensic checks and return the result dict."""
        findings: list[EvidenceItem] = []
        findings.extend(self._check_metadata())
        findings.extend(self._check_whitebox_edits())
        findings.extend(self._check_font_inconsistency())
        findings.extend(self._check_duplicate_images())
        findings.extend(self._check_incremental_updates())

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
                    values={"page": page_num + 1, "whitebox_count": len(overlapping)},
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


def _ev_to_dict(ev: EvidenceItem) -> dict:
    return ev.model_dump(mode="json")


# --------------------------------------------------------------------------
# Convenience function (used by the endpoint and the test suite)
# --------------------------------------------------------------------------

def analyze_pdf(path: str, doc_type: str = "other", filename: Optional[str] = None) -> dict:
    """Analyze a PDF file at `path` and return the forensics result dict.

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
        return da.analyze()
