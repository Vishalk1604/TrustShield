"""Phase 3 offline training script - Isolation Forest + Gradient-Boosted classifier.

Usage (from repo root):
    .venv/Scripts/python.exe -m services.risk.train

Reads: data/synthetic/labels.json + data/synthetic/packets/<PKT-*>/
Writes: services/risk/models/{isolation_forest,gradient_boosting,feature_scaler}.joblib
        services/risk/models/{feature_names,metrics}.json

All computation is local; no network calls.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np

# paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = Path(__file__).resolve().parent / "models"
PACKETS_DIR = REPO_ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = REPO_ROOT / "data" / "synthetic" / "labels.json"

MODELS_DIR.mkdir(exist_ok=True)

# avoid import errors when run as __main__
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.risk.app.features import FEATURE_NAMES, compute_features_batch  # noqa: E402


def _build_dataset() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Extract features for all 33 synthetic packets."""
    labels: dict[str, dict] = json.loads(LABELS_PATH.read_text())
    print(f"Extracting features from {len(labels)} packets ...")
    t0 = time.time()
    X, y, ids = compute_features_batch(PACKETS_DIR, labels)
    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s - X shape {X.shape}")
    return X, y, ids


def _train_isolation_forest(
    X_clean: np.ndarray,
    scaler,
) -> object:
    """Fit Isolation Forest on clean packets only (novelty detection)."""
    from sklearn.ensemble import IsolationForest

    X_scaled = scaler.transform(X_clean)
    isoforest = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
    isoforest.fit(X_scaled)
    return isoforest


def _cv_metrics(clf, X: np.ndarray, y: np.ndarray) -> dict:
    """5-fold stratified cross-validation metrics."""
    from sklearn.metrics import (
        classification_report,
        confusion_matrix,
        roc_auc_score,
    )
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    y_prob = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    auc = roc_auc_score(y, y_prob)
    cm = confusion_matrix(y, y_pred).tolist()
    report = classification_report(y, y_pred, target_names=["clean", "fraud"], output_dict=True)

    print(f"\n  ROC-AUC (5-fold CV): {auc:.4f}")
    print(f"  Confusion matrix:\n    TN={cm[0][0]} FP={cm[0][1]}\n    FN={cm[1][0]} TP={cm[1][1]}")
    print(f"  Clean  precision={report['clean']['precision']:.2f} recall={report['clean']['recall']:.2f}")
    print(f"  Fraud  precision={report['fraud']['precision']:.2f} recall={report['fraud']['recall']:.2f}")

    return {"roc_auc_cv": round(auc, 4), "confusion_matrix": cm, "classification_report": report}


def _iso_metrics(
    isoforest,
    scaler,
    X: np.ndarray,
    y: np.ndarray,
    ids: list[str],
) -> dict:
    """Evaluate Isolation Forest anomaly score separation between clean/fraud."""
    X_scaled = scaler.transform(X)
    raw_scores = isoforest.score_samples(X_scaled)  # more negative = more anomalous

    # Flip sign so higher = more anomalous
    anomaly_scores = -raw_scores

    clean_scores = anomaly_scores[y == 0]
    fraud_scores = anomaly_scores[y == 1]

    print(f"\n  IF anomaly score - clean mean={clean_scores.mean():.3f}, "
          f"fraud mean={fraud_scores.mean():.3f}")
    print(f"  IF score range: clean [{clean_scores.min():.3f}, {clean_scores.max():.3f}] "
          f"| fraud [{fraud_scores.min():.3f}, {fraud_scores.max():.3f}]")

    return {
        "clean_mean": round(float(clean_scores.mean()), 4),
        "clean_max": round(float(clean_scores.max()), 4),
        "fraud_mean": round(float(fraud_scores.mean()), 4),
        "fraud_min": round(float(fraud_scores.min()), 4),
    }


def _top_features(clf, n: int = 10) -> list[dict]:
    """Extract top-N feature importances from a fitted GBC/RF."""
    importances = clf.feature_importances_
    indices = np.argsort(importances)[::-1][:n]
    result = []
    for i in indices:
        result.append({"feature": FEATURE_NAMES[i], "importance": round(float(importances[i]), 4)})
    print("\n  Top feature importances:")
    for item in result[:5]:
        print(f"    {item['feature']:35s} {item['importance']:.4f}")
    return result


def main() -> None:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler

    print("=" * 60)
    print("TrustShield Phase 3 - Model Training")
    print("=" * 60)

    # 1. Build feature matrix
    X, y, ids = _build_dataset()
    n_clean = (y == 0).sum()
    n_fraud = (y == 1).sum()
    print(f"\nDataset: {n_clean} clean, {n_fraud} fraud, {len(FEATURE_NAMES)} features")

    # 2. Scale features (needed for Isolation Forest; also benefits GBC)
    scaler = StandardScaler()
    X_clean = X[y == 0]
    scaler.fit(X_clean)  # fit scaler on CLEAN packets only (IF's training distribution)
    X_scaled = scaler.transform(X)

    # 3. Isolation Forest - trained on clean packets only
    print("\n-- Isolation Forest (novelty detection on clean) --")
    isoforest = _train_isolation_forest(X_clean, scaler)
    iso_metrics = _iso_metrics(isoforest, scaler, X, y, ids)

    # 4. Supervised Gradient Boosting Classifier -- trained on all labeled packets
    print("\n-- Gradient Boosting Classifier (supervised, all packets) --")
    gbc = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        subsample=0.8, random_state=42,
    )
    gbc.fit(X_scaled, y)

    cv_metrics = _cv_metrics(gbc, X_scaled, y)
    top_features = _top_features(gbc)

    # 5. Persist models + metadata
    joblib.dump(isoforest, MODELS_DIR / "isolation_forest.joblib")
    joblib.dump(gbc, MODELS_DIR / "gradient_boosting.joblib")
    joblib.dump(scaler, MODELS_DIR / "feature_scaler.joblib")

    (MODELS_DIR / "feature_names.json").write_text(json.dumps(FEATURE_NAMES, indent=2))

    metrics = {
        "n_packets": int(len(ids)),
        "n_clean": int(n_clean),
        "n_fraud": int(n_fraud),
        "n_features": len(FEATURE_NAMES),
        "isolation_forest": iso_metrics,
        "gradient_boosting": cv_metrics,
        "top_features": top_features,
    }
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print("\n-- Summary --")
    print(f"  Models saved to {MODELS_DIR.relative_to(REPO_ROOT)}/")
    print(f"  ROC-AUC (CV): {cv_metrics['roc_auc_cv']:.4f}")
    auc_pass = cv_metrics["roc_auc_cv"] >= 0.80
    print(f"  AUC >= 0.80 check: {'PASS' if auc_pass else 'FAIL'}")
    print("=" * 60)

    if not auc_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
