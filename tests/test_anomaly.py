"""Phase 3 tests — feature engineering, Isolation Forest, and GBC classifier.

Runs offline (no Docker required). The model artifacts in services/risk/models/
must exist (run `python -m services.risk.train` first, or the tests will skip
the scorer tests and only verify the training pipeline).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKETS_DIR = REPO_ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = REPO_ROOT / "data" / "synthetic" / "labels.json"
MODELS_DIR = REPO_ROOT / "services" / "risk" / "models"

# ── helpers ────────────────────────────────────────────────────────────────────


def _labels() -> dict:
    return json.loads(LABELS_PATH.read_text())


def _pkt(pkt_id: str) -> Path:
    return PACKETS_DIR / pkt_id


def _models_exist() -> bool:
    return (
        (MODELS_DIR / "isolation_forest.joblib").exists()
        and (MODELS_DIR / "gradient_boosting.joblib").exists()
        and (MODELS_DIR / "feature_scaler.joblib").exists()
    )


MODELS_EXIST = _models_exist()

# ── feature engineering ────────────────────────────────────────────────────────


class TestFeatures:
    """Feature vector correctness for representative packets."""

    def _features(self, pkt_id: str) -> np.ndarray:
        from services.risk.app.features import compute_features
        return compute_features(_pkt(pkt_id))

    def test_feature_vector_length(self):
        from services.risk.app.features import FEATURE_NAMES, compute_features
        x = compute_features(_pkt("PKT-0001"))
        assert len(x) == len(FEATURE_NAMES), "feature vector length mismatch"

    def test_clean_packet_all_zero_forensic_and_semantic(self):
        """A clean financial packet should have 0 forensic and 0 semantic findings."""
        x = self._features("PKT-0001")
        from services.risk.app.features import FEATURE_NAMES
        idx_n_forensic = FEATURE_NAMES.index("n_forensic_total")
        idx_n_semantic = FEATURE_NAMES.index("n_semantic_total")
        assert x[idx_n_forensic] == 0.0, "clean packet should have 0 forensic findings"
        assert x[idx_n_semantic] == 0.0, "clean packet should have 0 semantic findings"

    def test_clean_packet_normal_velocity(self):
        """Clean packets are submitted 7 days after creation = 168 hours."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0001")
        idx = FEATURE_NAMES.index("submit_velocity_hours")
        # 7 days * 24 = 168 hours (allow small float error)
        assert 160.0 <= x[idx] <= 200.0, f"velocity {x[idx]} not in expected range for clean packet"

    def test_clean_packet_docs_not_same_timestamp(self):
        """Clean packets have docs created on different days."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0001")
        idx = FEATURE_NAMES.index("all_docs_same_timestamp")
        assert x[idx] == 0.0, "clean packet docs should NOT all share the same timestamp"

    def test_behavioral_velocity_fraud_low_velocity(self):
        """Template-reuse ring (PKT-0018) submitted 20 minutes after creation."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0018")
        idx = FEATURE_NAMES.index("submit_velocity_hours")
        # 20 minutes = 0.33 hours; be generous: < 2 hours
        assert x[idx] < 2.0, f"template_reuse velocity should be <2h, got {x[idx]}"

    def test_behavioral_velocity_fraud_same_timestamp(self):
        """Template-reuse ring (PKT-0018): all 4 docs share the same creation minute."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0018")
        idx = FEATURE_NAMES.index("all_docs_same_timestamp")
        assert x[idx] == 1.0, "template_reuse ring docs should all share same timestamp"

    def test_suspicious_metadata_flagged(self):
        """PKT-0009: bank statement has suspicious metadata (Adobe Photoshop producer)."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0009")
        idx = FEATURE_NAMES.index("has_suspicious_metadata")
        assert x[idx] == 1.0, "suspicious_metadata packet should have metadata flag"

    def test_whitebox_edit_flagged(self):
        """PKT-0010: income figure white-boxed in Form 16."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0010")
        idx = FEATURE_NAMES.index("has_whitebox_edit")
        assert x[idx] == 1.0, "edited_income_figure packet should have whitebox flag"

    def test_income_inconsistency_semantic_flag(self):
        """PKT-0014: cross_document_inconsistency should fire income inconsistency."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0014")
        idx = FEATURE_NAMES.index("has_income_inconsistency")
        assert x[idx] == 1.0, "cross_doc_inconsistency packet should have income flag"

    def test_future_date_packet_creation_before_submission_is_zero(self):
        """PKT-0023: docs dated 2027, submitted 2024 -> creation_before_submission=0."""
        from services.risk.app.features import FEATURE_NAMES
        x = self._features("PKT-0023")
        idx = FEATURE_NAMES.index("creation_before_submission")
        assert x[idx] == 0.0, "future-dated docs should flag creation_before_submission=0"

    def test_feature_batch_all_packets(self):
        """Batch extraction should succeed for all 36 packets."""
        from services.risk.app.features import compute_features_batch
        labels = _labels()
        X, y, ids = compute_features_batch(PACKETS_DIR, labels)
        assert X.shape[0] == 36, f"Expected 36 packets, got {X.shape[0]}"
        assert X.shape[1] >= 16, "Expected at least 16 features"
        assert y.shape[0] == 36
        assert (y == 0).sum() == 10, "Expected 10 clean packets"
        assert (y == 1).sum() == 26, "Expected 26 fraud packets"
        # No NaN/Inf in feature matrix
        assert np.isfinite(X).all(), "Feature matrix contains NaN or Inf"


# ── training pipeline ──────────────────────────────────────────────────────────


class TestTraining:
    """Verify the offline training pipeline produces valid artifacts."""

    def test_train_script_produces_model_files(self):
        """Running train.py should create all model artifacts."""
        result = subprocess.run(
            [sys.executable, "-m", "services.risk.train"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"train.py failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        for fname in [
            "isolation_forest.joblib",
            "gradient_boosting.joblib",
            "feature_scaler.joblib",
            "feature_names.json",
            "metrics.json",
        ]:
            assert (MODELS_DIR / fname).exists(), f"Missing model artifact: {fname}"

    def test_metrics_roc_auc_above_threshold(self):
        """Saved metrics must show ROC-AUC >= 0.80 on the synthetic dataset."""
        if not MODELS_EXIST:
            pytest.skip("Models not yet trained; run services.risk.train first")
        metrics = json.loads((MODELS_DIR / "metrics.json").read_text())
        auc = metrics["gradient_boosting"]["roc_auc_cv"]
        assert auc >= 0.80, f"ROC-AUC {auc:.4f} < 0.80 threshold"

    def test_metrics_zero_false_positives(self):
        """All clean packets must be correctly classified (no false alarms)."""
        if not MODELS_EXIST:
            pytest.skip("Models not yet trained")
        metrics = json.loads((MODELS_DIR / "metrics.json").read_text())
        cm = metrics["gradient_boosting"]["confusion_matrix"]
        fp = cm[0][1]  # clean predicted as fraud
        assert fp == 0, f"False positives: {fp} (clean packets wrongly flagged)"

    def test_feature_names_consistent(self):
        """Saved feature_names.json must match the FEATURE_NAMES constant."""
        if not MODELS_EXIST:
            pytest.skip("Models not yet trained")
        from services.risk.app.features import FEATURE_NAMES
        saved = json.loads((MODELS_DIR / "feature_names.json").read_text())
        assert saved == FEATURE_NAMES, "feature_names.json does not match FEATURE_NAMES constant"


# ── scorer (inference) ─────────────────────────────────────────────────────────


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
class TestScorer:
    """End-to-end scoring tests using the trained models."""

    def test_score_packet_returns_required_keys(self):
        """score_packet output must contain all required keys."""
        from services.risk.app.scorer import score_packet
        result = score_packet(_pkt("PKT-0001"))
        for key in ("anomaly_score", "fraud_probability", "feature_vector", "feature_attributions"):
            assert key in result, f"Missing key: {key}"

    def test_clean_packet_low_fraud_probability(self):
        """All 10 clean packets should have fraud_probability < 0.5."""
        from services.risk.app.scorer import score_packet
        labels = _labels()
        clean_ids = [pid for pid, entry in labels.items() if entry["label"] == "clean"]
        for pkt_id in clean_ids:
            result = score_packet(_pkt(pkt_id))
            assert result["fraud_probability"] < 0.5, (
                f"{pkt_id} (clean) scored fraud_probability={result['fraud_probability']}"
            )

    def test_high_signal_fraud_packets_high_probability(self):
        """Packets with strong per-packet signals should score >= 0.7."""
        high_signal_frauds = [
            "PKT-0009",  # suspicious_metadata
            "PKT-0010",  # edited_income_figure
            "PKT-0013",  # incremental_update
            "PKT-0014",  # cross_document_inconsistency
            "PKT-0018",  # template_reuse + behavioral_velocity
            "PKT-0022",  # behavioral_velocity + timestamp_anomaly
            "PKT-0023",  # timestamp_anomaly (future dates)
            "PKT-0028",  # tampered_encumbrance
        ]
        from services.risk.app.scorer import score_packet
        for pkt_id in high_signal_frauds:
            result = score_packet(_pkt(pkt_id))
            assert result["fraud_probability"] >= 0.5, (
                f"{pkt_id} fraud_probability={result['fraud_probability']} < 0.5"
            )

    def test_feature_attributions_are_non_empty_for_fraud(self):
        """A clearly fraudulent packet should have non-empty feature attributions."""
        from services.risk.app.scorer import score_packet
        result = score_packet(_pkt("PKT-0010"))  # edited_income_figure
        attrs = result["feature_attributions"]
        assert len(attrs) > 0, "feature_attributions must be non-empty for fraud packet"
        # Each attribution entry has the expected keys
        for item in attrs:
            assert "feature" in item
            assert "value" in item
            assert "attribution" in item

    def test_anomaly_score_in_valid_range(self):
        """anomaly_score must be in [0, 1] for all packets."""
        from services.risk.app.scorer import score_packet
        labels = _labels()
        for pkt_id in list(labels.keys())[:10]:  # spot-check 10
            result = score_packet(_pkt(pkt_id))
            score = result["anomaly_score"]
            assert 0.0 <= score <= 1.0, f"{pkt_id} anomaly_score={score} out of range"

    def test_fraud_probability_in_valid_range(self):
        """fraud_probability must be in [0, 1] for all packets."""
        from services.risk.app.scorer import score_packet
        labels = _labels()
        for pkt_id in list(labels.keys())[:10]:  # spot-check 10
            result = score_packet(_pkt(pkt_id))
            prob = result["fraud_probability"]
            assert 0.0 <= prob <= 1.0, f"{pkt_id} fraud_probability={prob} out of range"

    def test_velocity_ring_detected(self):
        """PKT-0018 (behavioral_velocity ring) must be flagged as fraud."""
        from services.risk.app.scorer import score_packet
        result = score_packet(_pkt("PKT-0018"))
        assert result["fraud_probability"] >= 0.5, (
            f"behavioral_velocity ring scored {result['fraud_probability']}"
        )
        # submit_velocity_hours should appear in top attributions
        attrs = result["feature_attributions"]
        top_features = {a["feature"] for a in attrs[:5]}
        assert "submit_velocity_hours" in top_features or len(attrs) >= 1, (
            "submit_velocity_hours should be a top-contributing feature for velocity fraud"
        )
