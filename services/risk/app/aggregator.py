"""Phase 4 — Trust Score Aggregation & Evidence Chain assembly.

Blends three explainable signal channels into a single 0-100 trust score
(100 = fully trustworthy, 0 = almost certainly fraudulent):

    1. FORENSIC  — per-document tamper findings (Phase 1 analyzer)
    2. SEMANTIC  — cross-document rule violations (Phase 2 rules engine)
    3. MODEL     — learned fraud probability (Phase 3 GBC) + IF novelty

The weighting is EXPLICIT and documented (see WEIGHTS below and DECISIONS.md).
The model's contribution is surfaced as its own evidence item with feature
attributions — never hidden inside the number.

Design principle baked in here: a FREEZE is only issued when there is concrete
document-level evidence (forensic or semantic). A high model probability with no
attributable document evidence (e.g. double-financing, which is purely relational)
is softened to MANUAL_REVIEW and explicitly routed to the cross-application graph
(Phase 5). This keeps the "never a hard action without explainable evidence" rule.

All computation is local; no network calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from shared.schemas import (
    Action,
    EvidenceCategory,
    EvidenceItem,
    PacketDecision,
    Recommendation,
    Severity,
    TrustScore,
)

SCORING_VERSION = "4.0.0"

# ── Explicit, documented weighting (sums to 1.0) ────────────────────────────────
# Rationale (see DECISIONS.md Phase 4):
#   model    0.55 — the calibrated learned signal; primary driver.
#   forensic 0.25 — deterministic per-document tamper evidence.
#   semantic 0.15 — deterministic cross-document evidence.
#   anomaly  0.05 — Isolation Forest novelty; weak (only 10 clean training packets).
WEIGHTS: dict[str, float] = {
    "model": 0.55,
    "forensic": 0.25,
    "semantic": 0.15,
    "anomaly": 0.05,
}

# Per-evidence-item risk penalty by severity (points subtracted from a 100 channel).
SEVERITY_PENALTY: dict[Severity, float] = {
    Severity.CRITICAL: 60.0,
    Severity.HIGH: 35.0,
    Severity.MEDIUM: 18.0,
    Severity.LOW: 6.0,
    Severity.INFO: 0.0,
}

# Recommendation thresholds (documented).
APPROVE_AT_OR_ABOVE = 70.0
FREEZE_BELOW = 40.0
# Any CRITICAL document finding caps trust at this ceiling (forces a freeze-band score).
CRITICAL_TRUST_CEILING = 25.0

# Phase 5: cross-application graph evidence is an ADDITIVE risk overlay on top of the
# per-packet blend (it does not steal weight from the per-packet channels, so Phase 4
# scores are unchanged when no graph evidence is present). A graph CRITICAL (e.g. a
# property pledged across >=3 applications) also triggers the CRITICAL_TRUST_CEILING.
GRAPH_OVERLAY_WEIGHT = 0.5

# Human-readable labels for model feature names (for the model evidence item).
FEATURE_LABELS: dict[str, str] = {
    "n_forensic_total": "number of document tamper signals",
    "n_forensic_high_critical": "number of severe tamper signals",
    "has_whitebox_edit": "white-box / overwrite edit detected",
    "has_font_inconsistency": "inconsistent font in a key figure",
    "has_duplicate_image": "duplicated (copy-pasted) content",
    "has_incremental_update": "post-hoc incremental PDF revision",
    "has_suspicious_metadata": "suspicious authoring software or dates",
    "n_semantic_total": "number of cross-document inconsistencies",
    "has_income_inconsistency": "declared income vs bank/salary mismatch",
    "has_property_irregularity": "property valuation / ID / LTV irregularity",
    "has_cersai_violation": "undisclosed registered charge (CERSAI)",
    "submit_velocity_hours": "submission timing relative to document creation",
    "max_doc_gap_days": "spread of document creation dates",
    "all_docs_same_timestamp": "all documents share one creation timestamp",
    "creation_before_submission": "document dates inconsistent with submission",
    "doc_count": "packet document count",
}


# ── risk helpers ────────────────────────────────────────────────────────────────

def _channel_risk(items: list[EvidenceItem]) -> float:
    """Convert a list of evidence items into a 0-1 risk for that channel.

    Sums severity penalties (capped at 100) and normalizes. A single CRITICAL
    item already yields 0.60 risk; multiple high-severity items saturate to 1.0.
    """
    if not items:
        return 0.0
    total = sum(SEVERITY_PENALTY.get(it.severity, 0.0) for it in items)
    return min(1.0, total / 100.0)


def _model_severity(prob: float) -> Severity:
    if prob >= 0.80:
        return Severity.HIGH
    if prob >= 0.50:
        return Severity.MEDIUM
    if prob >= 0.20:
        return Severity.LOW
    return Severity.INFO


def _build_model_evidence(
    fraud_probability: float,
    anomaly_score: float,
    attributions: list[dict],
    has_doc_evidence: bool,
) -> EvidenceItem:
    """Build the ANOMALY-category evidence item that surfaces the model's verdict."""
    # Top non-trivial attributions → human-readable factor list.
    top = [a for a in attributions if a.get("attribution", 0) > 0.01][:4]
    factor_phrases = [
        FEATURE_LABELS.get(a["feature"], a["feature"]) for a in top
    ]

    pct = round(fraud_probability * 100)
    if factor_phrases:
        factors_text = "; ".join(factor_phrases)
        desc = (
            f"The trained risk model assigns this packet a fraud probability of {pct}%. "
            f"Leading factors: {factors_text}."
        )
    elif fraud_probability >= 0.5:
        # High probability but no attributable document features — relational fraud signature.
        desc = (
            f"The trained risk model assigns this packet a fraud probability of {pct}%, "
            f"but no document-level factor explains it. This is the signature of relational "
            f"fraud (e.g. the same collateral pledged across applications) and should be "
            f"checked against the cross-application graph."
        )
    else:
        desc = (
            f"The trained risk model assigns this packet a low fraud probability of {pct}%. "
            f"No document tampering or cross-document inconsistency was detected."
        )

    return EvidenceItem(
        category=EvidenceCategory.ANOMALY,
        severity=_model_severity(fraud_probability),
        title="Learned risk model assessment",
        description=desc,
        source_location="risk model (gradient-boosted trees + isolation forest)",
        values={
            "fraud_probability": round(fraud_probability, 4),
            "anomaly_score": round(anomaly_score, 4),
            "top_factors": [
                {"factor": FEATURE_LABELS.get(a["feature"], a["feature"]),
                 "weight": a["attribution"]}
                for a in top
            ],
            "model_version": SCORING_VERSION,
        },
        confidence=round(max(fraud_probability, 1.0 - fraud_probability), 3),
    )


def _dedupe(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Drop exact-duplicate findings (same category + title + source location)."""
    seen: set[tuple] = set()
    out: list[EvidenceItem] = []
    for it in items:
        key = (it.category.value, it.title, it.source_location)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _recommend(
    trust: float,
    has_doc_evidence: bool,
    has_critical: bool,
) -> Recommendation:
    """Map a trust score to a recommended action with documented thresholds.

    Safeguard: a FREEZE requires concrete document-level evidence. A low score
    driven solely by the learned model (no forensic/semantic finding) is softened
    to MANUAL_REVIEW and routed to the cross-application graph — this is the
    signature of relational fraud (shared collateral / identity reuse) that only
    the Phase 5 graph can confirm.
    """
    thresholds = {
        "approve_at_or_above": APPROVE_AT_OR_ABOVE,
        "freeze_below": FREEZE_BELOW,
        "critical_trust_ceiling": CRITICAL_TRUST_CEILING,
        "weights": WEIGHTS,
    }

    if trust >= APPROVE_AT_OR_ABOVE:
        return Recommendation(
            action=Action.APPROVE,
            rationale=(
                f"Trust score {trust:.0f}/100 is at or above the approval threshold "
                f"({APPROVE_AT_OR_ABOVE:.0f}); no tampering or inconsistency of concern."
            ),
            thresholds_used=thresholds,
        )

    # Below approval. A FREEZE requires concrete document evidence (or a CRITICAL finding).
    if trust < FREEZE_BELOW and (has_doc_evidence or has_critical):
        return Recommendation(
            action=Action.FREEZE,
            rationale=(
                f"Trust score {trust:.0f}/100 is below the freeze threshold "
                f"({FREEZE_BELOW:.0f}) and is backed by concrete document-level evidence "
                f"(forensic and/or semantic findings). Recommend freezing pending investigation."
            ),
            thresholds_used=thresholds,
        )

    # Everything else is a MANUAL_REVIEW. When there is no document-level evidence, the
    # signal is model-only (relational/behavioral) — surface that and route to the graph.
    if not has_doc_evidence:
        rationale = (
            f"Trust score {trust:.0f}/100 is below approval, but it is driven by the learned "
            f"model with no attributable document-level evidence. This is consistent with "
            f"relational fraud (shared collateral / identity reuse). Route to the cross-application "
            f"graph review before any hard action."
        )
    else:
        rationale = (
            f"Trust score {trust:.0f}/100 falls between the freeze ({FREEZE_BELOW:.0f}) and approve "
            f"({APPROVE_AT_OR_ABOVE:.0f}) thresholds. Recommend manual underwriter review of the "
            f"flagged findings."
        )
    return Recommendation(
        action=Action.MANUAL_REVIEW,
        rationale=rationale,
        thresholds_used=thresholds,
    )


# ── public aggregation ──────────────────────────────────────────────────────────

def aggregate(
    packet_id: str,
    forensic_items: list[EvidenceItem],
    semantic_items: list[EvidenceItem],
    fraud_probability: float,
    anomaly_score: float,
    attributions: Optional[list[dict]] = None,
    graph_items: Optional[list[EvidenceItem]] = None,
) -> PacketDecision:
    """Blend all channels into a PacketDecision (score + evidence chain + recommendation).

    Args:
        packet_id: identifier for the packet.
        forensic_items: EvidenceItems from the Phase 1 analyzer (category=forensic).
        semantic_items: EvidenceItems from the Phase 2 rules engine (category=semantic).
        fraud_probability: Phase 3 GBC probability in [0, 1].
        anomaly_score: Phase 3 Isolation Forest novelty in [0, 1].
        attributions: optional model feature attributions (list of {feature, value, attribution}).
        graph_items: optional Phase 5 cross-application graph EvidenceItems (category=graph).
            Treated as an additive risk overlay; CRITICAL graph evidence (e.g. double-financed
            collateral) escalates exactly like a CRITICAL document finding.
    """
    attributions = attributions or []
    graph_items = graph_items or []

    # ── channel risks ──
    forensic_risk = _channel_risk(forensic_items)
    semantic_risk = _channel_risk(semantic_items)
    model_risk = max(0.0, min(1.0, fraud_probability))
    anomaly_risk = max(0.0, min(1.0, anomaly_score))

    blended_risk = (
        WEIGHTS["model"] * model_risk
        + WEIGHTS["forensic"] * forensic_risk
        + WEIGHTS["semantic"] * semantic_risk
        + WEIGHTS["anomaly"] * anomaly_risk
    )

    # Phase 5: additive graph overlay (does not dilute the per-packet channels).
    graph_risk = _channel_risk(graph_items)
    total_risk = min(1.0, blended_risk + GRAPH_OVERLAY_WEIGHT * graph_risk)

    trust = 100.0 * (1.0 - total_risk)

    # Critical override: any CRITICAL finding (document OR graph) caps trust into the freeze band.
    has_critical = any(
        it.severity == Severity.CRITICAL
        for it in (forensic_items + semantic_items + graph_items)
    )
    if has_critical:
        trust = min(trust, CRITICAL_TRUST_CEILING)

    trust = round(max(0.0, min(100.0, trust)), 1)

    # Concrete evidence = any forensic/semantic finding OR any non-INFO graph finding.
    # (An INFO "repeat applicant" graph note is context, not grounds for a hard action.)
    has_doc_evidence = bool(forensic_items or semantic_items) or any(
        it.severity != Severity.INFO for it in graph_items
    )

    # ── evidence chain assembly ──
    model_item = _build_model_evidence(
        fraud_probability, anomaly_score, attributions, has_doc_evidence
    )
    chain = _dedupe([*forensic_items, *semantic_items, *graph_items, model_item])
    # Order: most severe first, then by confidence.
    chain.sort(key=lambda e: (e.severity.rank, e.confidence), reverse=True)

    # ── sub-scores (each on a 0-100 trust scale) ──
    trust_score = TrustScore(
        overall=trust,
        forensic_subscore=round(100.0 * (1.0 - forensic_risk), 1),
        semantic_subscore=round(100.0 * (1.0 - semantic_risk), 1),
        anomaly_subscore=round(100.0 * (1.0 - model_risk), 1),
        version=SCORING_VERSION,
    )

    recommendation = _recommend(trust, has_doc_evidence, has_critical)

    return PacketDecision(
        packet_id=packet_id,
        trust_score=trust_score,
        evidence_chain=chain,
        recommendation=recommendation,
    )


def apply_verification(
    decision: PacketDecision,
    findings: list[EvidenceItem],
    penalty_points: float,
) -> PacketDecision:
    """Fold KYC/underwriting *consistency* findings into an existing authenticity decision.

    Completeness, identity/name-consistency and income-reconciliation gaps are consistency
    concerns, so they (a) join the evidence chain and (b) nudge the trust score down by an
    already-capped `penalty_points` (see underwriting.VERIFICATION_PENALTY_CAP) — never a tank.
    The recommendation is re-derived from the adjusted score. Eligibility (FOIR/LTV) is a
    business-rule outcome and is deliberately NOT passed in here — it must not move the trust score.
    """
    if not findings:
        return decision

    chain = _dedupe([*decision.evidence_chain, *findings])
    chain.sort(key=lambda e: (e.severity.rank, e.confidence), reverse=True)

    new_overall = decision.trust_score.overall - max(0.0, penalty_points)
    has_critical = any(it.severity == Severity.CRITICAL for it in chain)
    if has_critical:
        new_overall = min(new_overall, CRITICAL_TRUST_CEILING)
    new_overall = round(max(0.0, min(100.0, new_overall)), 1)

    # Concrete doc evidence now includes any non-INFO verification finding.
    has_doc_evidence = any(
        it.category in (EvidenceCategory.FORENSIC, EvidenceCategory.SEMANTIC)
        and it.severity != Severity.INFO
        for it in chain
    )
    recommendation = _recommend(new_overall, has_doc_evidence, has_critical)
    trust_score = decision.trust_score.model_copy(update={"overall": new_overall})
    return decision.model_copy(
        update={"trust_score": trust_score, "evidence_chain": chain,
                "recommendation": recommendation}
    )


def _deep_scan_findings(doc_path: Path, filename: str) -> list[EvidenceItem]:
    """Render any FLATTENED (no text layer) page of a packet doc and run the learned forgery model on it,
    so a raster forgery the text-layer forensics are blind to is still caught + localized. Evidence-only:
    these items are NOT fed to the risk feature vector (like re-OCR) — they surface in the evidence chain
    and the per-document viewer, and drive the forensic sub-score. Vector/text pages are skipped (the U-Net
    would false-fire on a pristine render; text-layer forensics already cover them)."""
    import io
    import tempfile

    import fitz
    from PIL import Image

    from services.forensics.app.image_forensics import analyze_image

    items: list[EvidenceItem] = []
    try:
        with fitz.open(doc_path) as d:
            for pno in range(d.page_count):
                if len(d[pno].get_text("text").strip()) >= 40:
                    continue
                pix = d[pno].get_pixmap(dpi=300)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB").save(tmp.name, "JPEG", quality=90)
                    tmp_path = tmp.name
                try:
                    res = analyze_image(tmp_path, learned="auto")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
                rw, rh = res.get("width") or 1, res.get("height") or 1
                for f in res.get("findings", []):
                    v = dict(f.get("values", {}) or {})
                    for r in v.get("regions", []) or []:
                        r["page"] = pno + 1
                        b = r.get("bbox")
                        if b:   # normalized box (resolution-independent) so any renderer can place it
                            r["bbox_frac"] = [b[0] / rw, b[1] / rh, b[2] / rw, b[3] / rh]
                    items.append(EvidenceItem(
                        category="forensic", severity=f.get("severity", "high"),
                        title=f.get("title", "Tampered region (learned forgery model)"),
                        description=f"{filename}: {f.get('description', '')}",
                        source_location=filename, values=v, confidence=float(f.get("confidence", 0.85)),
                    ))
    except Exception:  # pragma: no cover — render/torch failure must not sink scoring
        return items
    return items


def score_packet_dir(
    pkt_dir: Path,
    packet_id: Optional[str] = None,
    graph: object = None,
    deep_scan: bool = False,
) -> PacketDecision:
    """Full scoring for a synthetic packet directory (offline path).

    Runs Phase 1 forensics + Phase 2 semantic rules + Phase 3 model on the packet,
    then aggregates into a PacketDecision. If a Phase 5 ``graph`` (ApplicationGraph)
    is supplied, its cross-application evidence for this packet is folded in. With ``deep_scan=True`` the
    learned forgery model is also run on any flattened/image page (catches raster forgeries; evidence-only).
    """
    import json

    from services.forensics.app.analyzer import analyze_pdf
    from services.forensics.app.extractor import extract_entities
    from services.risk.app.features import compute_features
    from services.risk.app.rules import run_all_rules
    from services.risk.app.scorer import (
        anomaly_score as _anomaly,
        feature_attributions,
        fraud_probability as _fraud_prob,
    )

    pkt_dir = Path(pkt_dir)
    packet_id = packet_id or pkt_dir.name
    manifest = json.loads((pkt_dir / "manifest.json").read_text())
    gt = manifest.get("ground_truth", {})

    # Phase 1 forensic + Phase 2 entity extraction
    forensic_items: list[EvidenceItem] = []
    entities_by_doc: dict[str, dict] = {}
    for doc_rec in manifest.get("documents", []):
        doc_path = pkt_dir / doc_rec["filename"]
        if not doc_path.exists():
            continue
        doc_type = doc_rec.get("doc_type", "other")
        result = analyze_pdf(str(doc_path), doc_type=doc_type, filename=doc_rec["filename"])
        for f in result.get("findings", []):
            forensic_items.append(EvidenceItem(**f))
        if deep_scan:                                    # learned model on flattened/image pages (Part B)
            forensic_items.extend(_deep_scan_findings(doc_path, doc_rec["filename"]))
        entities_by_doc[doc_type] = extract_entities(str(doc_path), doc_type=doc_type)

    # Phase 2 semantic rules
    loan_amount: Optional[float] = gt.get("loan_amount")
    if loan_amount is None:
        for claims in gt.get("claims", {}).values():
            if "loan_amount" in claims:
                loan_amount = float(claims["loan_amount"])
                break
    semantic_items = run_all_rules(
        entities_by_doc, loan_amount=loan_amount, applicant_pan=gt.get("applicant_pan")
    )

    # Phase 3 model
    x = compute_features(pkt_dir)

    # Phase 5 graph evidence (optional)
    graph_items: list[EvidenceItem] = []
    if graph is not None:
        graph_items = graph.graph_evidence_for(packet_id)

    return aggregate(
        packet_id=packet_id,
        forensic_items=forensic_items,
        semantic_items=semantic_items,
        fraud_probability=_fraud_prob(x),
        anomaly_score=_anomaly(x),
        attributions=feature_attributions(x),
        graph_items=graph_items,
    )
