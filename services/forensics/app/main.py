"""TrustShield — Forensics + Ingestion service (Service A).

Phase 1: adds `POST /forensics/analyze` for per-document tamper detection.
Produces a list of EvidenceItems (forensic category) + a structural template fingerprint.

All analysis is local file I/O — no outbound network calls.
CORS is opened only for the local dashboard origin.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.privacy import install_log_redaction
from shared.schemas import EvidenceCategory
from services.forensics.app.analyzer import analyze_pdf
from services.forensics.app.image_forensics import analyze_image, compute_verdict
from services.forensics.app.ingest.loader import _IMAGE_EXTS
from services.forensics.app.ingest.pipeline import ingest_document

SERVICE_NAME = "forensics"
VERSION = "1.4.0"

_PDF_SUFFIXES = {".pdf"}
_IMAGE_SUFFIXES = set(_IMAGE_EXTS)

# Phase 7: scrub PII (PAN, account numbers, property IDs) from any log output.
install_log_redaction()

app = FastAPI(title="TrustShield Forensics Service", version=VERSION)

# Allow the local Vite dashboard to call this service directly. Localhost only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Health / root
# --------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Liveness probe used by Docker Compose and the dashboard."""
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/")
def root() -> dict:
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "evidence_category": EvidenceCategory.FORENSIC.value,
        "endpoints": {
            "analyze": "POST /forensics/analyze",
            "analyze_image": "POST /forensics/analyze-image",
            "ingest": "POST /forensics/ingest",
        },
        "docs": "/docs",
    }


# --------------------------------------------------------------------------
# Phase 1 — Analyze endpoint
# --------------------------------------------------------------------------

class AnalyzeByPathRequest(BaseModel):
    """Analyze a document already on the local filesystem (used for demo / test workflows)."""
    path: str
    doc_type: str = "other"
    filename: Optional[str] = None


@app.post("/forensics/analyze/path")
def analyze_by_path(req: AnalyzeByPathRequest) -> dict:
    """Analyze a PDF at a local path. Returns forensic findings + template fingerprint."""
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {req.path}")
    try:
        return analyze_pdf(str(p), doc_type=req.doc_type, filename=req.filename or p.name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/forensics/analyze")
async def analyze_upload(
    file: UploadFile = File(...),
    doc_type: str = Form(default="other"),
) -> dict:
    """Analyze an uploaded PDF. Accepts multipart/form-data with a 'file' part.

    Returns forensic findings + template fingerprint. Works on any document type
    (financial or legal/land).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Write to a temp file so fitz can open it by path (avoids size limits on stream open).
    suffix = Path(file.filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        return analyze_pdf(tmp_path, doc_type=doc_type, filename=file.filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# §10 / §6.D1 — Image-pixel forensics (scanned / photographed document edits)
# --------------------------------------------------------------------------

def _identifier_check(tmp_path: str) -> tuple[list[dict], dict]:
    """OCR the image + validate any ID number on it (PAN / Aadhaar) — a SEMANTIC tamper signal.

    Pixel forensics can't see an edit on a denoised, colored ID-card photo, but the *value* often
    gives it away: a PAN whose trailing letter was painted out is no longer a valid PAN, an Aadhaar
    that fails its checksum is invalid. This catches exactly those — independent of any pixel trace.
    Returns (findings, info). Never raises.
    """
    findings: list[dict] = []
    info: dict = {"ran": True}
    try:
        ing = ingest_document(tmp_path)
    except Exception as exc:
        return [], {"ran": False, "error": str(exc)}
    fields = ing.get("fields", {}) or {}
    kyc = ing.get("kyc", {}) or {}
    info.update({"doc_type": ing.get("doc_type"), "fields": {
        k: fields.get(k) for k in ("pan", "aadhaar", "name") if fields.get(k)}, "kyc": kyc})

    pan, pan_res = fields.get("pan"), kyc.get("pan")
    if pan and pan_res and not pan_res.get("valid"):
        findings.append({
            "category": "semantic", "severity": "high",
            "title": "Invalid ID number (possible alteration)",
            "description": (f"The PAN read from this document, '{pan}', is not a structurally valid "
                            f"PAN ({pan_res.get('reason')}). A genuine PAN is 10 characters in the "
                            f"form AAAAA9999A — the number may have been altered."),
            "source_location": "document identifier validation (OCR + PAN check)",
            "values": {"pan": pan, "reason": pan_res.get("reason")}, "confidence": 0.85})

    aad, aad_res = fields.get("aadhaar"), kyc.get("aadhaar")
    if aad and aad_res and not aad_res.get("valid"):
        findings.append({
            "category": "semantic", "severity": "high",
            "title": "Invalid Aadhaar number (possible alteration)",
            "description": (f"The Aadhaar number read from this document is not valid "
                            f"({aad_res.get('reason')}) — the digits may have been altered."),
            "source_location": "document identifier validation (OCR + Aadhaar/Verhoeff check)",
            "values": {"reason": aad_res.get("reason")}, "confidence": 0.8})

    # QR cross-verification: the card's QR encodes the real values; mismatch vs the printed/OCR'd text
    # (or an invalid Aadhaar UIDAI signature) is a strong tamper signal pixels can't see. Graceful:
    # if the QR is unreadable (dense code in a low-res photo) → no finding, never a false positive.
    try:
        from services.forensics.app.ingest.extract import qr_codes

        qr_findings, qr_info = qr_codes.qr_check(tmp_path, fields)
        info["qr"] = qr_info
        findings.extend(qr_findings)
    except Exception as exc:  # pragma: no cover
        info["qr"] = {"error": str(exc)}
    return findings, info


@app.post("/forensics/analyze-image")
async def analyze_image_upload(file: UploadFile = File(...)) -> dict:
    """Analyze an uploaded raster image (JPG/PNG/TIFF…) for tampering.

    Two complementary layers: (1) PIXEL forensics — ELA + noise-loss + copy-move + JPEG-ghost +
    flat-fill + EXIF (annotated overlay + ELA heatmap + per-detector signals); and (2) a SEMANTIC
    identifier check — OCR the image and validate any PAN/Aadhaar, which catches value edits the
    pixels can't see (e.g. a painted-out PAN character making the number invalid). Returns the merged
    findings + a combined verdict + trust. All local, no network.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")
    suffix = Path(file.filename).suffix.lower()
    if suffix and suffix not in _IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"not an image ({suffix}); use /forensics/analyze for PDFs")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    with tempfile.NamedTemporaryFile(suffix=suffix or ".png", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = analyze_image(tmp_path)
        # Semantic identifier check — merge any invalid-ID findings + recompute the combined verdict.
        id_findings, id_info = _identifier_check(tmp_path)
        result["identifier_check"] = id_info
        if id_findings:
            result["findings"] = id_findings + result.get("findings", [])
            result["verdict"], result["image_trust"] = compute_verdict(result["findings"])
        result["filename"] = file.filename
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# §7 — Real-document ingestion endpoint (multi-format intake → entities + KYC + forensics)
# --------------------------------------------------------------------------

def _ingest_one(content: bytes, filename: str, password: Optional[str]) -> dict:
    """Run the full ingestion (load → classify → extract → KYC) + forensics on one file."""
    suffix = Path(filename).suffix.lower() or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = ingest_document(tmp_path, password=password)
        result["filename"] = filename
        # PDFs → structural/text-layer forensics; images → pixel forensics (§6.D1/§10).
        if result.get("ok") and suffix in _PDF_SUFFIXES:
            try:
                fa = analyze_pdf(tmp_path, doc_type=result.get("doc_type", "other"),
                                 filename=filename)
                result["forensic"] = {
                    "template_fingerprint": fa.get("template_fingerprint"),
                    "findings": fa.get("findings", []),
                }
            except Exception as exc:  # forensics failure must not sink the whole ingest
                result["forensic"] = {"findings": [], "error": str(exc)}
        elif suffix in _IMAGE_SUFFIXES:
            try:
                ia = analyze_image(tmp_path)
                result["forensic"] = {"findings": ia.get("findings", [])}
                # The pixel-level detail (overlay, heatmap, verdict) rides alongside.
                result["image_forensics"] = {
                    k: ia.get(k) for k in
                    ("ok", "verdict", "image_trust", "signals", "annotated_b64", "ela_b64",
                     "width", "height")
                }
            except Exception as exc:
                result["forensic"] = {"findings": [], "error": str(exc)}
        else:
            result["forensic"] = {"findings": []}
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/forensics/ingest")
async def ingest_upload(
    files: list[UploadFile] = File(...),
    password: Optional[str] = Form(default=None),
) -> dict:
    """Ingest one or more REAL documents (PDF text/scan, or image).

    Per file: detect format → OCR if needed → infer doc_type → extract fields → validate
    identifiers (PAN/Aadhaar/IFSC) → run structural forensics (PDFs). Returns per-document
    entities + KYC + forensic findings — the input the dashboard renders and the risk
    service scores. `password` (optional) is applied to any encrypted PDF.
    """
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")

    documents: list[dict] = []
    for f in files:
        if not f.filename:
            continue
        content = await f.read()
        if not content:
            documents.append({"filename": f.filename, "ok": False, "error": "empty file"})
            continue
        documents.append(_ingest_one(content, f.filename, password))

    return {"documents": documents, "count": len(documents)}
