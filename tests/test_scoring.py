"""Phase 4 tests — trust score aggregation, evidence chain, and recommendations.

Covers:
  - aggregate() unit behavior (clean/approve, evidence-backed freeze, model-only review)
  - the critical-finding trust ceiling
  - the "no freeze without document evidence" safeguard (double-financing -> review)
  - end-to-end confusion matrix vs labels.json (every clean approves, every fraud flagged)
  - the schema contract (non-empty evidence chain on every decision)
  - the POST /risk/score endpoint
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.risk.app.aggregator import (
    APPROVE_AT_OR_ABOVE,
    CRITICAL_TRUST_CEILING,
    FREEZE_BELOW,
    WEIGHTS,
    aggregate,
    score_packet_dir,
)
from shared.schemas import (
    Action,
    EvidenceCategory,
    EvidenceItem,
    PacketDecision,
    Severity,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKETS_DIR = REPO_ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = REPO_ROOT / "data" / "synthetic" / "labels.json"
MODELS_DIR = REPO_ROOT / "services" / "risk" / "models"

MODELS_EXIST = (MODELS_DIR / "gradient_boosting.joblib").exists()


def _labels() -> dict:
    return json.loads(LABELS_PATH.read_text())


def _forensic(severity: Severity, title: str = "Tamper signal") -> EvidenceItem:
    return EvidenceItem(
        category=EvidenceCategory.FORENSIC, severity=severity,
        title=title, description="test forensic finding",
    )


def _semantic(severity: Severity, title: str = "Inconsistency") -> EvidenceItem:
    return EvidenceItem(
        category=EvidenceCategory.SEMANTIC, severity=severity,
        title=title, description="test semantic finding",
    )


# ── weight / threshold sanity ───────────────────────────────────────────────────


class TestWeightsAndThresholds:
    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "scoring weights must sum to 1.0"

    def test_thresholds_ordered(self):
        assert FREEZE_BELOW < APPROVE_AT_OR_ABOVE
        assert CRITICAL_TRUST_CEILING < FREEZE_BELOW


# ── aggregate() unit behavior ────────────────────────────────────────────────────


class TestAggregateUnit:
    def test_clean_packet_approves(self):
        """No findings + low model probability -> high trust + APPROVE."""
        dec = aggregate("PKT-X", [], [], fraud_probability=0.0, anomaly_score=0.2)
        assert dec.trust_score.overall >= APPROVE_AT_OR_ABOVE
        assert dec.recommendation.action == Action.APPROVE

    def test_clean_packet_still_has_evidence_chain(self):
        """Even a clean packet must carry a non-empty evidence chain (the model verdict)."""
        dec = aggregate("PKT-X", [], [], fraud_probability=0.0, anomaly_score=0.2)
        assert len(dec.evidence_chain) >= 1
        assert dec.evidence_chain[0].category == EvidenceCategory.ANOMALY

    def test_critical_finding_caps_trust(self):
        """A single CRITICAL finding forces trust to the freeze-band ceiling."""
        dec = aggregate(
            "PKT-X", [], [_semantic(Severity.CRITICAL)],
            fraud_probability=0.9, anomaly_score=0.3,
        )
        assert dec.trust_score.overall <= CRITICAL_TRUST_CEILING
        assert dec.recommendation.action == Action.FREEZE

    def test_document_evidence_low_score_freezes(self):
        """Low trust backed by forensic evidence -> FREEZE."""
        dec = aggregate(
            "PKT-X", [_forensic(Severity.HIGH), _forensic(Severity.HIGH)], [],
            fraud_probability=1.0, anomaly_score=0.3,
        )
        assert dec.trust_score.overall < FREEZE_BELOW
        assert dec.recommendation.action == Action.FREEZE

    def test_model_only_low_score_softens_to_review(self):
        """High model probability with NO document evidence must NOT auto-freeze.

        This is the relational-fraud safeguard: route to manual review / graph instead.
        """
        dec = aggregate("PKT-X", [], [], fraud_probability=1.0, anomaly_score=0.4)
        assert dec.recommendation.action == Action.MANUAL_REVIEW
        # rationale must explain the routing
        assert "graph" in dec.recommendation.rationale.lower()

    def test_subscores_populated(self):
        dec = aggregate(
            "PKT-X", [_forensic(Severity.HIGH)], [_semantic(Severity.MEDIUM)],
            fraud_probability=0.7, anomaly_score=0.3,
        )
        ts = dec.trust_score
        assert ts.forensic_subscore is not None
        assert ts.semantic_subscore is not None
        assert ts.anomaly_subscore is not None
        # forensic subscore should be lower than a clean 100 because of the HIGH finding
        assert ts.forensic_subscore < 100.0

    def test_evidence_chain_sorted_by_severity(self):
        dec = aggregate(
            "PKT-X",
            [_forensic(Severity.LOW, "low one"), _forensic(Severity.CRITICAL, "crit one")],
            [_semantic(Severity.MEDIUM, "med one")],
            fraud_probability=0.9, anomaly_score=0.3,
        )
        ranks = [e.severity.rank for e in dec.evidence_chain]
        assert ranks == sorted(ranks, reverse=True), "evidence chain must be severity-ordered"

    def test_dedupe_drops_exact_duplicates(self):
        dup = _forensic(Severity.HIGH, "same title")
        dup2 = _forensic(Severity.HIGH, "same title")
        dec = aggregate("PKT-X", [dup, dup2], [], fraud_probability=0.5, anomaly_score=0.3)
        forensic_titles = [e.title for e in dec.evidence_chain
                           if e.category == EvidenceCategory.FORENSIC]
        assert forensic_titles.count("same title") == 1, "exact duplicate findings must be deduped"

    def test_returns_valid_packet_decision(self):
        dec = aggregate("PKT-X", [_forensic(Severity.HIGH)], [], fraud_probability=0.8, anomaly_score=0.3)
        assert isinstance(dec, PacketDecision)
        # round-trips through schema validation
        PacketDecision.model_validate(dec.model_dump())


# ── end-to-end vs labels.json ────────────────────────────────────────────────────


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
class TestEndToEnd:
    def test_confusion_matrix_perfect_separation(self):
        """Every clean packet approves; every fraud packet is flagged (review|freeze)."""
        labels = _labels()
        tp = fp = tn = fn = 0
        for pid, entry in labels.items():
            dec = score_packet_dir(PACKETS_DIR / pid, pid)
            flagged = dec.recommendation.action in (Action.MANUAL_REVIEW, Action.FREEZE)
            is_fraud = entry["label"] == "fraud"
            if is_fraud and flagged:
                tp += 1
            elif is_fraud and not flagged:
                fn += 1
            elif (not is_fraud) and flagged:
                fp += 1
            else:
                tn += 1
        # No clean packet should be flagged, no fraud packet should slip through.
        assert fp == 0, f"{fp} clean packets wrongly flagged"
        assert fn == 0, f"{fn} fraud packets slipped through"
        assert tn == 10, f"expected 10 clean, got {tn}"
        assert tp == 26, f"expected 26 fraud flagged, got {tp}"

    def test_every_decision_has_evidence(self):
        """Contract: never a score without a non-empty evidence chain."""
        labels = _labels()
        for pid in labels:
            dec = score_packet_dir(PACKETS_DIR / pid, pid)
            assert len(dec.evidence_chain) >= 1, f"{pid} has empty evidence chain"

    def test_clean_packets_approve(self):
        labels = _labels()
        clean = [p for p, e in labels.items() if e["label"] == "clean"]
        for pid in clean:
            dec = score_packet_dir(PACKETS_DIR / pid, pid)
            assert dec.recommendation.action == Action.APPROVE, (
                f"{pid} (clean) -> {dec.recommendation.action} @ trust {dec.trust_score.overall}"
            )

    def test_tampered_encumbrance_freezes_on_critical(self):
        """PKT-0028 has a CRITICAL EC-vs-CERSAI finding -> trust capped, FREEZE."""
        dec = score_packet_dir(PACKETS_DIR / "PKT-0028", "PKT-0028")
        assert dec.trust_score.overall <= CRITICAL_TRUST_CEILING
        assert dec.recommendation.action == Action.FREEZE

    def test_double_financing_routes_to_review_not_freeze(self):
        """PKT-0031..33 (double_financing) have no document evidence -> MANUAL_REVIEW.

        The fraud is purely relational (shared collateral) so per-packet scoring must
        route to the graph rather than auto-freeze. This proves Phase 5 is necessary.
        """
        for pid in ("PKT-0031", "PKT-0032", "PKT-0033"):
            dec = score_packet_dir(PACKETS_DIR / pid, pid)
            assert dec.recommendation.action == Action.MANUAL_REVIEW, (
                f"{pid} should route to review, got {dec.recommendation.action}"
            )
            assert "graph" in dec.recommendation.rationale.lower()

    def test_edited_income_freezes_with_forensic_evidence(self):
        """PKT-0010 (white-boxed income) -> forensic evidence -> FREEZE."""
        dec = score_packet_dir(PACKETS_DIR / "PKT-0010", "PKT-0010")
        assert dec.recommendation.action == Action.FREEZE
        # the chain must contain a forensic item
        assert any(e.category == EvidenceCategory.FORENSIC for e in dec.evidence_chain)

    def test_model_evidence_item_present_for_every_packet(self):
        """Every decision surfaces the learned-model verdict as its own evidence item."""
        labels = _labels()
        for pid in list(labels)[:6]:
            dec = score_packet_dir(PACKETS_DIR / pid, pid)
            assert any(e.category == EvidenceCategory.ANOMALY for e in dec.evidence_chain), (
                f"{pid} missing model evidence item"
            )


# ── POST /risk/score endpoint ────────────────────────────────────────────────────


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
class TestScoreEndpoint:
    def _client(self):
        from fastapi.testclient import TestClient
        from services.risk.app.main import app
        return TestClient(app)

    def _doc_refs(self, pid: str) -> dict:
        manifest = json.loads((PACKETS_DIR / pid / "manifest.json").read_text())
        return {
            "packet_id": pid,
            "documents": [
                {
                    "path": str(PACKETS_DIR / pid / d["filename"]),
                    "doc_type": d["doc_type"],
                    "filename": d["filename"],
                }
                for d in manifest["documents"]
            ],
            "created_at": manifest.get("created_at"),
            "submitted_at": manifest.get("submitted_at"),
            "applicant_pan": manifest.get("ground_truth", {}).get("applicant_pan"),
            "loan_amount": manifest.get("ground_truth", {}).get("loan_amount"),
        }

    def test_score_clean_packet_endpoint(self):
        client = self._client()
        resp = client.post("/risk/score", json=self._doc_refs("PKT-0001"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["trust_score"]["overall"] >= APPROVE_AT_OR_ABOVE
        assert body["recommendation"]["action"] == "approve"
        assert len(body["evidence_chain"]) >= 1

    def test_score_fraud_packet_endpoint(self):
        client = self._client()
        resp = client.post("/risk/score", json=self._doc_refs("PKT-0010"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["recommendation"]["action"] in ("freeze", "manual_review")
        assert body["trust_score"]["overall"] < APPROVE_AT_OR_ABOVE

    def test_score_endpoint_missing_file_404(self):
        client = self._client()
        bad = {
            "packet_id": "X",
            "documents": [{"path": "does/not/exist.pdf", "doc_type": "form16",
                           "filename": "form16.pdf"}],
        }
        resp = client.post("/risk/score", json=bad)
        assert resp.status_code == 404
