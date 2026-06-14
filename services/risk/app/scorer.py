"""Phase 3 model inference — loads trained models and scores a packet.

Models are loaded once at module import time (not per-request).
Call `score_packet(pkt_dir)` from the risk service or tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Lazy singletons — populated on first call to avoid import-time I/O
_isoforest = None
_gbc = None
_scaler = None
_feature_names: Optional[list[str]] = None


def _load_models() -> None:
    global _isoforest, _gbc, _scaler, _feature_names
    if _isoforest is not None:
        return
    import joblib

    if not (_MODELS_DIR / "isolation_forest.joblib").exists():
        raise RuntimeError(
            "Models not found. Run: .venv/Scripts/python.exe -m services.risk.train"
        )
    _isoforest = joblib.load(_MODELS_DIR / "isolation_forest.joblib")
    _gbc = joblib.load(_MODELS_DIR / "gradient_boosting.joblib")
    _scaler = joblib.load(_MODELS_DIR / "feature_scaler.joblib")
    _feature_names = json.loads((_MODELS_DIR / "feature_names.json").read_text())


def anomaly_score(x: np.ndarray) -> float:
    """Return Isolation Forest anomaly score in [0, 1] (1 = most anomalous).

    IF raw score is flipped and scaled using the IF's offset so that:
      - clean packets (inliers) → score close to 0
      - fraud/novel packets (outliers) → score approaching 1
    """
    _load_models()
    x2d = x.reshape(1, -1)
    x_scaled = _scaler.transform(x2d)
    # decision_function > 0 → inlier, < 0 → outlier
    df = float(_isoforest.decision_function(x_scaled)[0])
    # Map from roughly [-0.5, 0.5] → [1, 0], clipped to [0, 1]
    score = float(np.clip(0.5 - df, 0.0, 1.0))
    return round(score, 4)


def fraud_probability(x: np.ndarray) -> float:
    """Return GBC fraud probability in [0, 1]."""
    _load_models()
    x2d = x.reshape(1, -1)
    x_scaled = _scaler.transform(x2d)
    prob = float(_gbc.predict_proba(x_scaled)[0][1])
    return round(prob, 4)


def feature_attributions(x: np.ndarray) -> list[dict]:
    """Return per-feature attribution scores for this prediction.

    Approximation: global_importance × |feature_value| (normalized).
    Sorted descending by |attribution|.
    """
    _load_models()
    importances = _gbc.feature_importances_
    # Normalize feature values to [0, 1] range using scaler mean/std
    x_norm = np.abs(_scaler.transform(x.reshape(1, -1))[0])
    attributions = importances * x_norm
    total = attributions.sum()
    if total > 0:
        attributions = attributions / total

    items = [
        {
            "feature": name,
            "value": round(float(x[i]), 4),
            "attribution": round(float(attributions[i]), 4),
        }
        for i, name in enumerate(_feature_names)
        if attributions[i] > 0
    ]
    items.sort(key=lambda d: d["attribution"], reverse=True)
    return items


def score_packet(pkt_dir: Path) -> dict:
    """Full Phase 3 scoring for a packet directory.

    Returns:
        {
          "anomaly_score": float,        # 0–1, IF novelty
          "fraud_probability": float,    # 0–1, GBC probability
          "feature_vector": [float, ...],
          "feature_attributions": [{feature, value, attribution}, ...],
        }
    """
    from services.risk.app.features import compute_features

    x = compute_features(pkt_dir)
    return {
        "anomaly_score": anomaly_score(x),
        "fraud_probability": fraud_probability(x),
        "feature_vector": x.tolist(),
        "feature_attributions": feature_attributions(x),
    }
