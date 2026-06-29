"""Format-agnostic document analysis (plan: full unification).

One entry point — `analyze_document` — that dispatches by file type and runs *every applicable* detector,
so the caller can drop a PDF or an image and get the same coverage:

  - **image** → `image_forensics.analyze_image` (pixel forensics + semantic ID/QR + the opt-in U-Net).
  - **PDF**   → `analyzer.analyze_pdf` (text-layer / structural: white-box redaction, font swap, re-OCR,
    metadata, duplicate-object) **plus** each page rasterised at 300 dpi and run through `analyze_image`
    (pixel forensics + the U-Net) — so a *flattened/repainted* PDF (no text layer for re-OCR to bite) is
    still caught by the learned model. Findings are merged into one verdict.

`deep=True` turns on the learned U-Net (`learned="auto"`); otherwise the heuristics-only zero-FP path runs.
Pure-local: PyMuPDF render + the existing analyzers. No network.
"""

from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path

import fitz
from PIL import Image

from services.forensics.app.analyzer import analyze_pdf
from services.forensics.app.image_forensics import analyze_image, compute_verdict

_PDF_SUFFIXES = {".pdf"}
RENDER_DPI = 300        # render PDF pages at the U-Net's native (300-dpi) training domain
_TEXT_MIN = 40          # chars of extractable text above which a page is "vector/text" (skip the raster pass:
                        # a vector render is pristine — out-of-distribution for the U-Net — and text-layer
                        # forensics already cover it; the raster/U-Net pass is for FLATTENED/image pages)


def _page_pdf_boxes(pdf_findings: list[dict], page_no: int, sx: float, sy: float) -> list[list[int]]:
    """Text-layer (PDF-point) regions for `page_no`, scaled to the rendered page's pixel space."""
    out: list[list[int]] = []
    for f in pdf_findings:
        for r in (f.get("values") or {}).get("regions") or []:
            if int(r.get("page", 1)) != page_no or not r.get("bbox"):
                continue
            b = r["bbox"]
            out.append([int(b[0] * sx), int(b[1] * sy), int(b[2] * sx), int(b[3] * sy)])
    return out


def analyze_document(path: str, *, deep: bool = False, doc_type: str = "other",
                     filename: str | None = None) -> dict:
    """Analyze a document (PDF or image). Returns an `analyze_image`-shaped superset; PDFs add `pages`."""
    learned = "auto" if deep else "env"
    suffix = Path(path).suffix.lower()
    if suffix not in _PDF_SUFFIXES:
        res = analyze_image(path, learned=learned)
        res.setdefault("kind", "image")
        return res

    # ── PDF: structural/text-layer + per-page raster (pixel + U-Net) ──
    pdf = analyze_pdf(path, doc_type=doc_type, filename=filename)
    pdf_findings = list(pdf.get("findings", []))
    all_findings = list(pdf_findings)
    pages: list[dict] = []
    deep_available = False
    try:
        with fitz.open(path) as doc:
            for pno in range(doc.page_count):
                page = doc[pno]
                pix = page.get_pixmap(dpi=RENDER_DPI)
                png = pix.tobytes("png")
                is_raster = len(page.get_text("text").strip()) < _TEXT_MIN   # no text layer → flattened/image page
                page_verdict, page_boxes = "CLEAN", []
                # raster/U-Net pass ONLY on flattened pages (vector renders are pristine → U-Net would FP)
                if is_raster:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                        Image.open(io.BytesIO(png)).convert("RGB").save(tmp.name, "JPEG", quality=90)
                        tmp_path = tmp.name
                    try:
                        img_res = analyze_image(tmp_path, learned=learned)
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)
                    lm = (img_res.get("signals") or {}).get("learned_model") or {}
                    deep_available = deep_available or bool(lm.get("available"))
                    rW, rH = img_res.get("width"), img_res.get("height")
                    page_verdict = img_res.get("verdict", "CLEAN")
                    for f in img_res.get("findings", []):
                        for r in (f.get("values") or {}).get("regions") or []:
                            r["page"] = pno + 1
                            if r.get("bbox"):
                                page_boxes.append([int(v) for v in r["bbox"]])
                        all_findings.append(f)
                    W, H = rW, rH                          # display in the U-Net's analysis space
                else:
                    W, H = pix.width, pix.height           # full render space

                pr = page.rect
                sx = (W / pr.width) if pr.width else 1.0
                sy = (H / pr.height) if pr.height else 1.0
                page_boxes += _page_pdf_boxes(pdf_findings, pno + 1, sx, sy)
                disp = Image.open(io.BytesIO(png)).convert("RGB")
                if (disp.width, disp.height) != (int(W), int(H)):
                    disp = disp.resize((int(W), int(H)))
                buf = io.BytesIO(); disp.save(buf, "JPEG", quality=85)
                pages.append({
                    "page": pno + 1, "w": int(W), "h": int(H),
                    "verdict": page_verdict, "boxes": page_boxes,
                    "img_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
                })
    except Exception as exc:  # pragma: no cover — rendering failure must not sink the PDF analysis
        all_findings.append({"severity": "info", "category": "forensic",
                             "title": "Raster pass skipped", "description": f"page render failed: {exc}",
                             "values": {}})

    verdict, trust = compute_verdict(all_findings)
    return {
        "ok": True, "kind": "pdf", "filename": filename,
        "page_count": pdf.get("page_count"), "template_fingerprint": pdf.get("template_fingerprint"),
        "findings": all_findings, "verdict": verdict, "image_trust": trust,
        "deep_used": deep, "deep_available": deep_available,
        "pages": pages,
    }
