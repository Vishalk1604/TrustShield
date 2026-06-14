"""Feature engineering for TrustShield risk models — Phase 3.

Converts the outputs of Phase 1 (forensic analysis) and Phase 2 (semantic rules)
plus metadata-level behavioral signals into a fixed-size numeric feature vector
suitable for scikit-learn models.

All computation is local; no network calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

# --------------------------------------------------------------------------
# Feature schema (keep in sync with FEATURE_NAMES; order matters for models)
# --------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    # --- Forensic signals (per-doc findings aggregated to packet level) ---
    "n_forensic_total",          # total forensic finding count across all docs
    "n_forensic_high_critical",  # high+critical forensic findings
    "has_whitebox_edit",         # any white-box / overlapping-object edit detected
    "has_font_inconsistency",    # any font inconsistency detected
    "has_duplicate_image",       # any copy-paste / duplicate image detected
    "has_incremental_update",    # any incremental-update revision detected
    "has_suspicious_metadata",   # suspicious producer, future date, or impossible dates
    # --- Semantic signals (cross-document rule violations) ---
    "n_semantic_total",          # total semantic finding count
    "has_income_inconsistency",  # income / bank / salary slip mismatch
    "has_property_irregularity", # property ID mismatch, valuation inflation, LTV violation
    "has_cersai_violation",      # EC-vs-CERSAI undisclosed charge
    # --- Behavioral / temporal signals ---
    "submit_velocity_hours",     # hours from earliest-doc-creation to submission (low = suspicious)
    "max_doc_gap_days",          # max days between any two doc creation dates (0 = mass-produced)
    "all_docs_same_timestamp",   # 1 if all docs share the same creation minute (1 = suspicious)
    "creation_before_submission",# 1 if EVERY doc was created before submission date (0 = anomaly)
    # --- Document completeness ---
    "doc_count",                 # number of documents in the packet
]


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string to UTC datetime."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _parse_pdf_date(date_str: str) -> Optional[datetime]:
    """Parse a PDF date string D:YYYYMMDDHHmmSS -> datetime."""
    import re
    if not date_str:
        return None
    s = date_str.strip()
    if s.startswith("D:"):
        s = s[2:]
    m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            tzinfo=timezone.utc,
        )
    except (ValueError, OverflowError):
        return None


# --------------------------------------------------------------------------
# Behavioral feature extraction
# --------------------------------------------------------------------------

def _resolve_doc_path(pkt_dir: Path, doc_rec: dict) -> Path:
    """Resolve a document's filesystem path.

    Prefers an explicit absolute ``abspath`` (used by the API path, where docs may
    not live under a common packet directory) and falls back to ``pkt_dir/filename``
    (the offline synthetic-packet layout).
    """
    if doc_rec.get("abspath"):
        return Path(doc_rec["abspath"])
    return pkt_dir / doc_rec["filename"]


def _behavioral_features(pkt_dir: Path, manifest: dict) -> dict[str, float]:
    """Extract temporal/behavioral features from the packet manifest and PDF metadata."""
    import fitz

    created_at = _parse_iso(manifest.get("created_at"))
    submitted_at = _parse_iso(manifest.get("submitted_at"))

    # Velocity: hours from packet creation to submission
    velocity_hours: float = 0.0
    if created_at and submitted_at:
        velocity_hours = (submitted_at - created_at).total_seconds() / 3600.0

    # Extract creation dates from each PDF's metadata
    doc_creation_dates: list[datetime] = []
    all_before_submission = True
    for doc_rec in manifest.get("documents", []):
        doc_path = _resolve_doc_path(pkt_dir, doc_rec)
        if not doc_path.exists():
            continue
        try:
            with fitz.open(str(doc_path)) as doc:
                meta = doc.metadata or {}
                cd = _parse_pdf_date(meta.get("creationDate", ""))
                if cd:
                    doc_creation_dates.append(cd)
                    if submitted_at and cd > submitted_at:
                        all_before_submission = False
        except Exception:
            continue

    max_gap_days: float = 0.0
    all_same_ts: float = 0.0
    if len(doc_creation_dates) >= 2:
        max_gap_days = float((max(doc_creation_dates) - min(doc_creation_dates)).days)
        # All docs within the same minute (to within 60s)?
        buckets = set(
            dt.replace(second=0, microsecond=0) for dt in doc_creation_dates
        )
        all_same_ts = 1.0 if len(buckets) == 1 else 0.0

    return {
        "submit_velocity_hours": float(max(0, velocity_hours)),
        "max_doc_gap_days": max_gap_days,
        "all_docs_same_timestamp": all_same_ts,
        "creation_before_submission": 1.0 if all_before_submission else 0.0,
        "doc_count": float(len(manifest.get("documents", []))),
    }


# --------------------------------------------------------------------------
# Public: compute feature vector for one packet
# --------------------------------------------------------------------------

def compute_features(pkt_dir: Path, manifest: Optional[dict] = None) -> np.ndarray:
    """Compute the feature vector for a packet.

    Runs Phase 1 (forensic analysis) and Phase 2 (semantic rules + entity extraction)
    on the packet, then combines with behavioral features into a numeric array.

    Args:
        pkt_dir: Base directory for resolving relative document filenames.
        manifest: Optional in-memory manifest dict (API path). When omitted, the
            packet's ``manifest.json`` is read from ``pkt_dir`` (offline path).
            Documents may carry an ``abspath`` to override ``pkt_dir/filename``.

    Returns:
        np.ndarray of shape (len(FEATURE_NAMES),), dtype float32.
    """
    from services.forensics.app.analyzer import analyze_pdf
    from services.forensics.app.extractor import extract_entities
    from services.risk.app.rules import run_all_rules

    if manifest is None:
        manifest = json.loads((pkt_dir / "manifest.json").read_text())

    # ---- Phase 1: Forensic analysis ----
    all_forensic: list[dict] = []
    entities_by_doc: dict[str, dict] = {}

    for doc_rec in manifest.get("documents", []):
        doc_path = _resolve_doc_path(pkt_dir, doc_rec)
        doc_type = doc_rec.get("doc_type", "other")
        if not doc_path.exists():
            continue
        # Forensic
        result = analyze_pdf(str(doc_path), doc_type=doc_type, filename=doc_rec["filename"])
        all_forensic.extend(result.get("findings", []))
        # Entity extraction
        ent = extract_entities(str(doc_path), doc_type=doc_type)
        entities_by_doc[doc_type] = ent

    # ---- Phase 2: Semantic rules ----
    gt = manifest.get("ground_truth", {})
    pan = gt.get("applicant_pan")
    # Loan amount: try top-level first (property packets), then per-doc claims
    loan_amount: Optional[float] = None
    if gt.get("loan_amount") is not None:
        loan_amount = float(gt["loan_amount"])
    else:
        for claims in gt.get("claims", {}).values():
            if "loan_amount" in claims:
                loan_amount = float(claims["loan_amount"])
                break

    semantic_items = run_all_rules(entities_by_doc, loan_amount=loan_amount, applicant_pan=pan)

    # ---- Aggregate forensic features ----
    n_forensic = len(all_forensic)
    n_forensic_hc = sum(
        1 for f in all_forensic if f.get("severity") in ("high", "critical")
    )
    titles_lower = [f.get("title", "").lower() for f in all_forensic]

    has_whitebox = float(any("white" in t or "covered" in t for t in titles_lower))
    has_font = float(any("font" in t for t in titles_lower))
    has_dup_img = float(any("duplicate" in t or "copy" in t for t in titles_lower))
    has_incr = float(any("incremental" in t for t in titles_lower))
    has_meta = float(any(
        kw in t for t in titles_lower
        for kw in ("suspicious", "future", "impossible", "modified long")
    ))

    # ---- Aggregate semantic features ----
    n_semantic = len(semantic_items)
    sem_titles = [s.title.lower() for s in semantic_items]

    has_income = float(any("income" in t or "bank" in t or "salary" in t for t in sem_titles))
    has_prop_irr = float(any(
        kw in t for t in sem_titles
        for kw in ("property", "valuation", "ltv", "loan-to-value", "registry")
    ))
    has_cersai = float(any("cersai" in t or "encumbrance" in t for t in sem_titles))

    # ---- Behavioral features ----
    beh = _behavioral_features(pkt_dir, manifest)

    # ---- Assemble vector (must match FEATURE_NAMES order exactly) ----
    vec = [
        float(n_forensic),
        float(n_forensic_hc),
        has_whitebox,
        has_font,
        has_dup_img,
        has_incr,
        has_meta,
        float(n_semantic),
        has_income,
        has_prop_irr,
        has_cersai,
        beh["submit_velocity_hours"],
        beh["max_doc_gap_days"],
        beh["all_docs_same_timestamp"],
        beh["creation_before_submission"],
        beh["doc_count"],
    ]
    return np.array(vec, dtype=np.float32)


def compute_features_batch(
    packets_dir: Path,
    labels: dict[str, dict],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Compute features for all packets.

    Returns:
        X: (n_packets, n_features) array
        y: (n_packets,) int array — 0 = clean, 1 = fraud
        pkt_ids: list of packet IDs in the same order as X/y rows
    """
    Xs, ys, ids = [], [], []
    for pkt_id, entry in labels.items():
        pkt_dir = packets_dir / pkt_id
        if not pkt_dir.exists():
            continue
        try:
            x = compute_features(pkt_dir)
            label = 0 if entry.get("label") == "clean" else 1
            Xs.append(x)
            ys.append(label)
            ids.append(pkt_id)
        except Exception as exc:
            print(f"  WARN: feature extraction failed for {pkt_id}: {exc}")
    return np.vstack(Xs), np.array(ys, dtype=int), ids
