"""OCR engine swap-point (plan.md §7).

Week 1 delegates to local **Tesseract** (via `app.ocr`). Week 2 (Person 2, GPU) replaces
the internals with **PaddleOCR PP-OCRv4 + PP-Structure** for layout/table-aware OCR —
callers (loader, extractors) only use the functions here, so the swap is transparent.
"""

from __future__ import annotations

from services.forensics.app import ocr as _tess


def engine_name() -> str:
    """Active OCR engine identifier (for logs / response metadata)."""
    return "tesseract" if _tess.tesseract_available() else "none"


def available() -> bool:
    return _tess.tesseract_available()


def page_to_text(page, dpi: int = 200) -> str:
    """OCR a single PyMuPDF page."""
    return _tess.ocr_page(page, dpi=dpi)


def image_file_to_text(path: str) -> str:
    """OCR a standalone image file (JPG/PNG/TIFF/...)."""
    return _tess.ocr_image_file(path)
