"""TrustShield — Risk + Scoring service (Service B).

Phase 2: `POST /risk/rules/check` — cross-document semantic consistency analysis.
Phase 4: `POST /risk/score` — the main orchestration endpoint. Blends forensic +
semantic + learned-model signals into a 0-100 TrustScore with an ordered, deduplicated
evidence chain and a recommended action (the full PacketDecision envelope).

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
VERSION = "4.0.0"

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
        "endpoints": {
            "rules_check": "POST /risk/rules/check",
            "score": "POST /risk/score",
        },
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


# --------------------------------------------------------------------------
# Phase 4 — Trust Score Aggregation (main orchestration endpoint)
# --------------------------------------------------------------------------

class ScoreRequest(BaseModel):
    """Score a full packet: blend forensic + semantic + model signals.

    Documents are referenced by local path (consistent with the local-only contract).
    ``created_at``/``submitted_at`` enable the behavioral (velocity) features; omit
    them and those features fall back to neutral values.
    """
    packet_id: Optional[str] = None
    documents: list[DocumentRef]
    loan_amount: Optional[float] = None
    applicant_pan: Optional[str] = None
    created_at: Optional[str] = None
    submitted_at: Optional[str] = None


@app.post("/risk/score")
def risk_score(req: ScoreRequest) -> dict:
    """Run the full TrustShield pipeline on a packet and return a PacketDecision.

    Pipeline: Phase 1 forensic analysis (per doc) + Phase 2 semantic rules
    (cross-doc) + Phase 3 learned model (fraud probability + novelty) ->
    Phase 4 aggregation into a 0-100 TrustScore + ordered evidence chain +
    recommended action. Never returns a score without a non-empty evidence chain.
    """
    from services.forensics.app.analyzer import analyze_pdf
    from services.forensics.app.extractor import extract_entities
    from services.risk.app.aggregator import aggregate
    from services.risk.app.features import compute_features
    from services.risk.app.rules import run_all_rules
    from services.risk.app.scorer import (
        anomaly_score,
        feature_attributions,
        fraud_probability,
    )
    from shared.schemas import EvidenceItem

    # Validate all paths exist.
    for doc in req.documents:
        if not Path(doc.path).exists():
            raise HTTPException(status_code=404, detail=f"File not found: {doc.path}")

    packet_id = req.packet_id or "packet"

    # ---- Phase 1 forensic + Phase 2 entity extraction ----
    forensic_items: list[EvidenceItem] = []
    entities_by_doc: dict[str, dict] = {}
    for doc in req.documents:
        try:
            result = analyze_pdf(doc.path, doc_type=doc.doc_type, filename=doc.filename)
            for f in result.get("findings", []):
                forensic_items.append(EvidenceItem(**f))
            entities_by_doc[doc.doc_type] = extract_entities(doc.path, doc.doc_type)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Analysis failed for {doc.filename}: {exc}"
            ) from exc

    # Resolve applicant_pan: prefer explicit, fall back to extracted.
    pan = req.applicant_pan
    if not pan:
        for dt in ("identity", "form16"):
            pan = entities_by_doc.get(dt, {}).get("pan")
            if pan:
                break

    # ---- Phase 2 semantic rules ----
    semantic_items = run_all_rules(
        entities_by_doc, loan_amount=req.loan_amount, applicant_pan=pan
    )

    # ---- Phase 3 learned model (build features from an in-memory manifest) ----
    base_dir = Path(req.documents[0].path).parent
    manifest = {
        "documents": [
            {"filename": d.filename, "doc_type": d.doc_type, "abspath": d.path}
            for d in req.documents
        ],
        "created_at": req.created_at,
        "submitted_at": req.submitted_at,
        "ground_truth": {
            "applicant_pan": pan,
            "loan_amount": req.loan_amount,
            "claims": {},
        },
    }
    try:
        x = compute_features(base_dir, manifest=manifest)
        fraud_prob = fraud_probability(x)
        anom = anomaly_score(x)
        attributions = feature_attributions(x)
    except RuntimeError as exc:
        # Models not trained yet.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # ---- Phase 4 aggregation ----
    decision = aggregate(
        packet_id=packet_id,
        forensic_items=forensic_items,
        semantic_items=semantic_items,
        fraud_probability=fraud_prob,
        anomaly_score=anom,
        attributions=attributions,
    )

    return decision.model_dump(mode="json")
