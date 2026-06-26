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
import shutil
from typing import Optional

import fitz  # PyMuPDF


def _resolve_tesseract_cmd() -> str:
    """Locate the Tesseract binary across host (Windows) and container (Linux).

    Order: explicit TESSERACT_CMD env → the Windows host install if present → a
    `tesseract` on PATH (Linux/Docker, where the Dockerfile apt-installs it) →
    a bare "tesseract" (let pytesseract resolve via PATH).
    """
    env = os.environ.get("TESSERACT_CMD")
    if env:
        return env
    win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(win):
        return win
    return shutil.which("tesseract") or "tesseract"


# Tesseract binary path — overridable via env for Docker/CI.
TESSERACT_CMD = _resolve_tesseract_cmd()

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


def ocr_region(page: "fitz.Page", rect: "fitz.Rect", dpi: int = 300, pad: float = 4.0) -> str:
    """OCR a small clip of a page (e.g. one value's bbox + a little padding), at high DPI since the
    crop is tiny. Used by the re-OCR cross-check to confirm whether a specific value is actually
    rendered at its location (full-page OCR can drop a small number on a dense page). Returns '' on
    failure / when OCR is unavailable."""
    if not tesseract_available():
        return ""
    try:
        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        clip = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
        pix = page.get_pixmap(clip=clip, dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, config="--psm 7")   # treat the crop as a single line
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


def ocr_image_file(path: str) -> str:
    """OCR an image file (JPG/PNG/TIFF/...). Returns '' if OCR is unavailable or fails."""
    if not tesseract_available():
        return ""
    try:
        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        with Image.open(path) as img:
            return pytesseract.image_to_string(img)
    except Exception:
        return ""
