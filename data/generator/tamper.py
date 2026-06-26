"""Forge specific, detectable tamper signals into otherwise-clean synthetic PDFs.

Each function corresponds to a real-world forgery technique and a Phase 1 forensic detector:

| function                | forged signal                              | detected in Phase 1 by         |
|-------------------------|--------------------------------------------|--------------------------------|
| make_metadata_suspicious| producer = editing tool; modDate >> create | metadata / mod-software trace  |
| edit_money_figure       | white-box redaction + redrawn number       | overlapping-object / font scan |
| edit_money_figure(font=)| number drawn in a different font than body | font-inconsistency scan        |
| duplicate_seal          | identical image bytes inserted twice       | duplicate-object (copy-paste)  |
| incremental_overlay     | incremental save → extra xref / %%EOF      | incremental-update detection   |

Everything is synthetic. No network, no real PII.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF

from data.generator.pdf_builder import (
    FONT_ALT,
    FONT_BODY,
    MARGIN_X,
    PAGE_W,
    _money,
    apply_metadata,
    DocMeta,
)

WHITE = (1, 1, 1)

# Plausible "forging tool" producer strings — a legitimate bank statement would not carry these.
SUSPICIOUS_PRODUCERS = [
    "Adobe Photoshop 24.0 (Windows)",
    "iLovePDF",
    "PDFescape Online",
    "Foxit PhantomPDF",
]


def make_metadata_suspicious(
    doc: "fitz.Document",
    *,
    producer: str,
    creation_date: datetime,
    mod_date: datetime,
    title: str = "Bank Statement",
) -> None:
    """Overwrite metadata so the producer looks like an image/PDF editor and the document was
    modified well after it was created."""
    meta = DocMeta(
        producer=producer,
        creator=producer,
        author="Issuing Institution",
        title=title,
        creation_date=creation_date,
        mod_date=mod_date,
    )
    apply_metadata(doc, meta)


def edit_money_figure(
    doc: "fitz.Document",
    old_amount: float,
    new_amount: float,
    *,
    page_index: int = 0,
    font: str = FONT_BODY,
) -> bool:
    """White-box the printed `old_amount` and redraw `new_amount` on top.

    Returns True if the figure was found and edited. Pass `font=FONT_ALT` to also inject a
    font inconsistency (the new number is in a serif font while the body is sans-serif).
    """
    page = doc[page_index]
    old_text = _money(old_amount)
    rects = page.search_for(old_text)
    if not rects:
        return False
    new_text = _money(new_amount)
    # Cover EVERY printed occurrence of the original number (a realistic Form 16 shows the gross figure
    # in more than one place — Part A summary + Part B), then redraw the forged value on top of each.
    # Covering them all is what a real forger does AND is what makes the edit detectable: the original
    # survives only in the text layer, so the render→OCR cross-check sees it nowhere on the page.
    for r in rects:
        size = max(7.0, min(13.0, (r.y1 - r.y0) * 0.92))   # match the local font size
        page.draw_rect(fitz.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 30, r.y1 + 2), color=WHITE, fill=WHITE, width=0)
        page.insert_text((r.x0, r.y1 - 1), new_text, fontname=font, fontsize=size)
    return True


def edit_text(
    doc: "fitz.Document",
    find: str,
    replace: str,
    *,
    page_index: int = 0,
    font: str = FONT_BODY,
    size: float = 11.0,
    cover_to_margin: bool = False,
) -> bool:
    """White-box the printed `find` text and redraw `replace` on top.

    Used for forged-title (alter the owner name) and tampered-EC (white-box a real charge row and
    stamp 'NIL'). The original `find` text stays in the content/text layer — that residue is the
    forensic signal. Set `cover_to_margin` to wipe the whole row to the right margin.
    """
    page = doc[page_index]
    rects = page.search_for(find)
    if not rects:
        return False
    r = rects[0]
    right = (PAGE_W - MARGIN_X) if cover_to_margin else (r.x1 + 30)
    page.draw_rect(fitz.Rect(r.x0 - 2, r.y0 - 2, right, r.y1 + 2), color=WHITE, fill=WHITE, width=0)
    if replace:
        page.insert_text((r.x0, r.y1 - 1), replace, fontname=font, fontsize=size)
    return True


def duplicate_seal(
    doc: "fitz.Document", seal_png: bytes, *, page_index: int = 0
) -> None:
    """Insert the same seal image twice — identical image bytes are a copy-paste fingerprint."""
    page = doc[page_index]
    page.insert_image(fitz.Rect(430, 700, 502, 772), stream=seal_png)
    page.insert_image(fitz.Rect(340, 700, 412, 772), stream=seal_png)  # the pasted duplicate


def incremental_overlay(path: str, *, note: str = "verified") -> None:
    """Reopen a saved PDF, overlay a small change, and save incrementally so the file gains an
    extra cross-reference section / %%EOF — the hallmark of an after-the-fact revision."""
    doc = fitz.open(path)
    page = doc[0]
    # A tiny stamp at the bottom — content is unimportant; the *incremental save* is the signal.
    page.insert_text((60, 800), note, fontname=FONT_ALT, fontsize=8, color=(0.6, 0.6, 0.6))
    doc.save(path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    doc.close()


def pick_producer(index: int) -> str:
    """Deterministically pick a suspicious producer string."""
    return SUSPICIOUS_PRODUCERS[index % len(SUSPICIOUS_PRODUCERS)]
