"""Local OCR helpers — shared by the extractor (Phase 2) and the forensic re-OCR
cross-check (roadmap §6.D2).

Everything here is a local subprocess (Tesseract) + in-memory image work: no network.
Every entry point degrades gracefully — if Tesseract or Pillow is unavailable, the
functions return empty/false rather than raising, so the surrounding pipeline keeps
working (the re-OCR check simply no-ops, the extractor falls back to embedded text).
"""

from __future__ import annotations

import io
import os
from typing import Optional

import fitz  # PyMuPDF

# Tesseract binary path — overridable via env for Docker/CI; defaults to the Windows host install.
TESSERACT_CMD = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)

_AVAILABLE: Optional[bool] = None  # cached availability probe


def tesseract_available() -> bool:
    """Return True if pytesseract + Pillow import and the Tesseract binary responds.

    Result is cached after the first call. Never raises.
    """
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        pytesseract.get_tesseract_version()
        _AVAILABLE = True
    except Exception:
        _AVAILABLE = False
    return _AVAILABLE


def render_page_png(page: "fitz.Page", dpi: int = 200) -> bytes:
    """Render a PyMuPDF page to PNG bytes. Pure PyMuPDF — no Tesseract needed."""
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


def ocr_page(page: "fitz.Page", dpi: int = 200) -> str:
    """Render one page and OCR it. Returns '' if OCR is unavailable or fails."""
    if not tesseract_available():
        return ""
    try:
        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        img = Image.open(io.BytesIO(render_page_png(page, dpi=dpi)))
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def ocr_pdf(path: str, dpi: int = 200) -> str:
    """OCR every page of a PDF at `path` and join the text. Returns '' on failure."""
    if not tesseract_available():
        return ""
    try:
        with fitz.open(path) as doc:
            return "\n".join(ocr_page(page, dpi=dpi) for page in doc)
    except Exception:
        return ""
