"""TrustShield — Forensics + Ingestion service (Service A).

Phase 0: health endpoint + shared-schema wiring check only. The tamper-detection endpoints
(`POST /forensics/analyze`, template fingerprinting, OCR) arrive in Phases 1–2.

Local-only: this service makes no outbound network calls. CORS is opened only for the local
dashboard origin so the browser UI can reach it.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importing the shared contract here also proves the PYTHONPATH wiring works inside the container.
from shared.schemas import EvidenceCategory

SERVICE_NAME = "forensics"
VERSION = "0.0.0"

app = FastAPI(title="TrustShield Forensics Service", version=VERSION)

# Allow the local Vite dashboard to call this service directly. Localhost only — never a remote host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness probe used by Docker Compose and the dashboard."""
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/")
def root() -> dict:
    return {
        "service": SERVICE_NAME,
        "message": "TrustShield Forensics — Phase 0 placeholder. Analysis endpoints land in Phase 1.",
        "evidence_category": EvidenceCategory.FORENSIC.value,
        "docs": "/docs",
    }
