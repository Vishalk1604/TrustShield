"""TrustShield — Risk + Scoring service (Service B).

Phase 2: `POST /risk/rules/check` — cross-document semantic consistency analysis.
Phase 4: `POST /risk/score` — the main orchestration endpoint. Blends forensic +
semantic + learned-model signals into a 0-100 TrustScore with an ordered, deduplicated
evidence chain and a recommended action (the full PacketDecision envelope).

All analysis is local — no outbound network calls. CERSAI verification uses the local mock
adapter in shared/mocks/.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.schemas import Action

SERVICE_NAME = "risk"
VERSION = "5.0.0"


def _graph_store_path() -> Path:
    """Path to the persisted cross-application graph (override via env for tests)."""
    default = Path(__file__).resolve().parent.parent / "graph_store" / "app_graph.pkl"
    return Path(os.environ.get("TRUSTSHIELD_GRAPH_STORE", str(default)))

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
            "graph_upsert": "POST /risk/graph/upsert",
            "graph_clusters": "GET /risk/graph/clusters",
            "graph_subgraph": "GET /risk/graph/subgraph/{packet_id}",
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
    employer: Optional[str] = None
    created_at: Optional[str] = None
    submitted_at: Optional[str] = None
    use_graph: bool = False


@app.post("/risk/score")
def risk_score(req: ScoreRequest) -> dict:
    """Run the full TrustShield pipeline on a packet and return a PacketDecision.

    Pipeline: Phase 1 forensic analysis (per doc) + Phase 2 semantic rules
    (cross-doc) + Phase 3 learned model (fraud probability + novelty) ->
    Phase 4 aggregation into a 0-100 TrustScore + ordered evidence chain +
    recommended action. When ``use_graph`` is set, the packet is upserted into the
    persisted cross-application graph (Phase 5) and its relational evidence
    (double-financed collateral, fraud rings) is folded into the decision.
    Never returns a score without a non-empty evidence chain.
    """
    from services.forensics.app.analyzer import analyze_pdf
    from services.forensics.app.extractor import extract_entities
    from services.risk.app.aggregator import aggregate
    from services.risk.app.features import compute_features
    from services.risk.app.graph import ApplicationGraph
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
    template_fingerprints: set[str] = set()
    for doc in req.documents:
        try:
            result = analyze_pdf(doc.path, doc_type=doc.doc_type, filename=doc.filename)
            for f in result.get("findings", []):
                forensic_items.append(EvidenceItem(**f))
            if result.get("template_fingerprint"):
                template_fingerprints.add(result["template_fingerprint"])
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

    # ---- Phase 5 cross-application graph (optional) ----
    graph_items: list[EvidenceItem] = []
    if req.use_graph:
        property_ids = {
            ent.get("property_id")
            for ent in entities_by_doc.values()
            if ent.get("property_id")
        }
        graph = ApplicationGraph.load(_graph_store_path())
        graph.upsert_application(
            packet_id,
            applicant_pan=pan,
            employer=req.employer or entities_by_doc.get("form16", {}).get("employer"),
            property_ids=property_ids,
            template_fingerprints=template_fingerprints,
        )
        graph.save(_graph_store_path())
        graph_items = graph.graph_evidence_for(packet_id)

    # ---- Phase 4 aggregation ----
    decision = aggregate(
        packet_id=packet_id,
        forensic_items=forensic_items,
        semantic_items=semantic_items,
        fraud_probability=fraud_prob,
        anomaly_score=anom,
        attributions=attributions,
        graph_items=graph_items,
    )

    return decision.model_dump(mode="json")


# --------------------------------------------------------------------------
# Phase 5 — Cross-application graph endpoints
# --------------------------------------------------------------------------

class GraphUpsertRequest(BaseModel):
    """Add or update one application's nodes/edges in the cross-application graph."""
    packet_id: str
    applicant_pan: Optional[str] = None
    employer: Optional[str] = None
    property_ids: list[str] = []
    template_fingerprints: list[str] = []


@app.post("/risk/graph/upsert")
def graph_upsert(req: GraphUpsertRequest) -> dict:
    """Upsert one application into the persisted cross-application graph."""
    from services.risk.app.graph import ApplicationGraph

    graph = ApplicationGraph.load(_graph_store_path())
    graph.upsert_application(
        req.packet_id,
        applicant_pan=req.applicant_pan,
        employer=req.employer,
        property_ids=req.property_ids,
        template_fingerprints=req.template_fingerprints,
    )
    graph.save(_graph_store_path())
    return {"packet_id": req.packet_id, "ok": True, "n_applications": len(graph._app_nodes())}


@app.get("/risk/graph/clusters")
def graph_clusters() -> dict:
    """Return all surfaced fraud rings and double-financed-collateral clusters."""
    from services.risk.app.graph import ApplicationGraph

    graph = ApplicationGraph.load(_graph_store_path())
    return graph.clusters()


@app.get("/risk/graph/subgraph/{packet_id}")
def graph_subgraph(packet_id: str) -> dict:
    """Return a small subgraph around one application for visualisation."""
    from services.risk.app.graph import ApplicationGraph

    graph = ApplicationGraph.load(_graph_store_path())
    return graph.subgraph_for(packet_id)


# --------------------------------------------------------------------------
# Phase 6 — Demo endpoints (drive the investigator dashboard over the synthetic set)
# --------------------------------------------------------------------------
# These let the browser score the committed synthetic packets by id (the browser
# cannot hand local file paths to the backend). They read only local synthetic data.

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _synthetic_dirs() -> tuple[Path, Path]:
    root = _repo_root()
    return root / "data" / "synthetic" / "packets", root / "data" / "synthetic" / "labels.json"


@app.get("/risk/demo/packets")
def demo_packets() -> dict:
    """List the synthetic packets available to score (for the dashboard picker)."""
    import json

    packets_dir, labels_path = _synthetic_dirs()
    if not labels_path.exists():
        raise HTTPException(status_code=404, detail="Synthetic labels.json not found.")
    labels = json.loads(labels_path.read_text())

    out = []
    for pkt_id, entry in labels.items():
        manifest_path = packets_dir / pkt_id / "manifest.json"
        applicant = None
        n_docs = 0
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            applicant = m.get("applicant_name")
            n_docs = len(m.get("documents", []))
        out.append({
            "packet_id": pkt_id,
            "applicant_name": applicant,
            "n_docs": n_docs,
            # ground truth — shown in the UI as a "known label" chip for demo verification
            "ground_truth_label": entry.get("label"),
            "ground_truth_fraud_types": entry.get("fraud_types", []),
        })
    return {"packets": out, "count": len(out)}


@app.post("/risk/demo/seed")
def demo_seed() -> dict:
    """(Re)build the cross-application graph from all synthetic packets and persist it.

    The dashboard calls this once so ring/collateral clusters are populated before scoring.
    """
    import json

    from services.risk.app.graph import ApplicationGraph

    packets_dir, labels_path = _synthetic_dirs()
    if not labels_path.exists():
        raise HTTPException(status_code=404, detail="Synthetic labels.json not found.")
    labels = json.loads(labels_path.read_text())
    graph = ApplicationGraph.build_from_packets(packets_dir, labels)
    graph.save(_graph_store_path())
    clusters = graph.clusters()
    return {
        "seeded": True,
        "n_applications": clusters["n_applications"],
        "collateral_clusters": len(clusters["collateral_clusters"]),
        "employer_rings": len(clusters["employer_rings"]),
    }


@app.post("/risk/demo/score/{packet_id}")
def demo_score(packet_id: str, use_graph: bool = True) -> dict:
    """Score one synthetic packet by id and return the decision + its graph subgraph."""
    from services.risk.app.aggregator import score_packet_dir
    from services.risk.app.graph import ApplicationGraph

    packets_dir, _ = _synthetic_dirs()
    pkt_dir = packets_dir / packet_id
    if not (pkt_dir / "manifest.json").exists():
        raise HTTPException(status_code=404, detail=f"Unknown packet: {packet_id}")

    graph = None
    subgraph = {"nodes": [], "edges": []}
    if use_graph:
        graph = ApplicationGraph.load(_graph_store_path())
        if not graph.G.has_node(f"app:{packet_id}"):
            # Graph not seeded yet — build it on the fly so clusters are present.
            import json

            _, labels_path = _synthetic_dirs()
            labels = json.loads(labels_path.read_text())
            graph = ApplicationGraph.build_from_packets(packets_dir, labels)
            graph.save(_graph_store_path())
        subgraph = graph.subgraph_for(packet_id)

    try:
        decision = score_packet_dir(pkt_dir, packet_id, graph=graph)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"decision": decision.model_dump(mode="json"), "subgraph": subgraph}
