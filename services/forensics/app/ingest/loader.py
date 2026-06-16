"""Multi-format document intake (plan.md §7).

Turns any uploaded file into text + metadata, regardless of whether it is a digital-born
text PDF, a scanned/image-only PDF, a phone photo (JPG/PNG/TIFF), or a password-protected
PDF. Per PDF page it uses the embedded text layer when present (fast path) and falls back
to OCR for image-only pages. PyMuPDF handles standard PDF passwords via `authenticate()`,
so no extra dependency is needed for the common case.

Returns a `LoadedDoc` with the combined text and how it was obtained — the rest of the
pipeline (classify → extract) consumes `text` and doesn't care about the source format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from services.forensics.app.ingest import ocr_engine

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_MIN_PAGE_TEXT = 15  # chars of embedded text below which a page is treated as image-only


@dataclass
class LoadedDoc:
    text: str = ""
    kind: str = "pdf"                 # "pdf" | "image"
    page_count: int = 0
    source: str = "embedded"          # "embedded" | "ocr" | "mixed" | "image-ocr"
    ocr_used: bool = False
    needs_password: bool = False      # encrypted PDF and no/!wrong password supplied
    error: Optional[str] = None
    per_page_source: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.needs_password


def load_text(path: str, password: Optional[str] = None) -> LoadedDoc:
    """Load a document and return its text + provenance. Never raises."""
    ext = Path(path).suffix.lower()
    if ext in _IMAGE_EXTS:
        return _load_image(path)
    return _load_pdf(path, password=password)


def _load_image(path: str) -> LoadedDoc:
    text = ocr_engine.image_file_to_text(path)
    if not text.strip():
        return LoadedDoc(kind="image", page_count=1, source="image-ocr", ocr_used=True,
                         error="image OCR produced no text (illegible or OCR unavailable)")
    return LoadedDoc(text=text, kind="image", page_count=1, source="image-ocr",
                     ocr_used=True, per_page_source=["image-ocr"])


def _load_pdf(path: str, password: Optional[str] = None) -> LoadedDoc:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        return LoadedDoc(error=f"could not open PDF: {exc}")

    try:
        if doc.needs_pass:
            if not password or doc.authenticate(password) == 0:
                return LoadedDoc(kind="pdf", needs_password=True,
                                 error="PDF is password-protected — supply the correct password")

        parts: list[str] = []
        per_page: list[str] = []
        ocr_used = False
        for page in doc:
            embedded = page.get_text("text") or ""
            if len(embedded.strip()) >= _MIN_PAGE_TEXT:
                parts.append(embedded)
                per_page.append("embedded")
            else:
                ocr_txt = ocr_engine.page_to_text(page)
                parts.append(ocr_txt)
                per_page.append("ocr")
                if ocr_txt.strip():
                    ocr_used = True

        text = "\n".join(parts)
        sources = set(per_page)
        source = "embedded" if sources == {"embedded"} else (
            "ocr" if sources == {"ocr"} else "mixed"
        )
        ld = LoadedDoc(text=text, kind="pdf", page_count=doc.page_count, source=source,
                       ocr_used=ocr_used, per_page_source=per_page)
        if not text.strip():
            ld.error = "no text recoverable (image-only PDF and OCR unavailable/illegible)"
        return ld
    finally:
        if not doc.is_closed:
            doc.close()
