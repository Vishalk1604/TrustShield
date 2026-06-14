"""TrustShield — Risk + Scoring service (Service B).

Phase 2: adds `POST /risk/rules/check` for cross-document semantic consistency analysis.
Returns semantic EvidenceItems from the financial and property/legal rules engine.

All analysis is local — no outbound network calls. CERSAI verification uses the local mock
adapter in shared/mocks/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.schemas import Action

SERVICE_NAME = "risk"
VERSION = "2.0.0"

app = FastAPI(title="TrustShield Risk Service", version=VERSION)

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
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/")
def root() -> dict:
    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "actions": [a.value for a in Action],
        "endpoints": {"rules_check": "POST /risk/rules/check"},
        "docs": "/docs",
    }


# --------------------------------------------------------------------------
# Phase 2 — Semantic rules check
# --------------------------------------------------------------------------

class DocumentRef(BaseModel):
    path: str
    doc_type: str
    filename: str


class RulesCheckRequest(BaseModel):
    """Analyze semantic consistency across an entire packet's documents."""
    packet_id: Optional[str] = None
    documents: list[DocumentRef]
    loan_amount: Optional[float] = None
    applicant_pan: Optional[str] = None


@app.post("/risk/rules/check")
def rules_check(req: RulesCheckRequest) -> dict:
    """Run cross-document semantic consistency rules on a packet.

    For each document, extracts entities (income, PAN, property ID, etc.) then applies:
    - Financial: Form16 vs bank vs salary slip income consistency; name/PAN consistency.
    - Property/legal: owner vs applicant; property ID consistency; LTV sanity;
      encumbrance certificate vs CERSAI registry.

    Returns a list of semantic EvidenceItems (may be empty for a clean packet).
    """
    from services.forensics.app.extractor import extract_entities
    from services.risk.app.rules import run_all_rules

    # Validate all paths exist.
    for doc in req.documents:
        if not Path(doc.path).exists():
            raise HTTPException(status_code=404, detail=f"File not found: {doc.path}")

    # Extract entities from each document.
    entities_by_doc: dict[str, dict] = {}
    for doc in req.documents:
        try:
            ent = extract_entities(doc.path, doc.doc_type)
            entities_by_doc[doc.doc_type] = ent
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Extraction failed for {doc.filename}: {exc}",
            ) from exc

    # Resolve applicant_pan: prefer explicit, fall back to extracted.
    pan = req.applicant_pan
    if not pan:
        for dt in ("identity", "form16"):
            pan = entities_by_doc.get(dt, {}).get("pan")
            if pan:
                break

    # Run all semantic rules.
    findings = run_all_rules(entities_by_doc, loan_amount=req.loan_amount, applicant_pan=pan)

    return {
        "packet_id": req.packet_id,
        "entities_extracted": {k: {fk: fv for fk, fv in v.items()
                                    if not fk.startswith("_")}
                                for k, v in entities_by_doc.items()},
        "findings": [f.model_dump(mode="json") for f in findings],
        "finding_count": len(findings),
    }
