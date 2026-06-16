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
from services.forensics.app.ingest.pipeline import ingest_document

SERVICE_NAME = "forensics"
VERSION = "1.2.0"

_PDF_SUFFIXES = {".pdf"}

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
        # Structural/tamper forensics run on PDFs (image-level forensics is a later milestone).
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
