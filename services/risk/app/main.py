"""TrustShield — Risk + Scoring service (Service B).

Phase 0: health endpoint + shared-schema wiring check only. The rules engine, Isolation Forest
anomaly model, NetworkX cross-application graph, and the orchestration endpoint
(`POST /risk/score` → TrustScore + evidence chain + recommendation) arrive in Phases 2–5.

Local-only: no outbound network calls. CORS opened only for the local dashboard origin.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.schemas import Action

SERVICE_NAME = "risk"
VERSION = "0.0.0"

app = FastAPI(title="TrustShield Risk Service", version=VERSION)

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
        "message": "TrustShield Risk — Phase 0 placeholder. Scoring endpoints land in Phases 2–5.",
        "actions": [a.value for a in Action],
        "docs": "/docs",
    }
