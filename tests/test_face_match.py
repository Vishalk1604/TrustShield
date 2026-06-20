"""Cross-document face matching (plan §10 Phase 6).

The face library is optional, so the embedding step is exercised only when it's installed; the
comparison LOGIC (same person vs different) is pure and tested deterministically with synthetic vectors.
"""

import numpy as np

from services.forensics.app.ingest.extract import face_match


def test_same_person_no_finding():
    v = np.array([1.0, 0.2, -0.3, 0.5], dtype=np.float32)
    assert face_match.compare_embeddings({"pan": v, "aadhaar": v.copy()}) == []


def test_different_people_flagged():
    a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)   # orthogonal → distance ~1.0
    findings = face_match.compare_embeddings({"pan": a, "aadhaar": b})
    assert findings and findings[0]["severity"] == "high"
    assert findings[0]["values"]["detector"] == "face_match"
    assert set(findings[0]["values"]["docs"]) == {"pan", "aadhaar"}


def test_similar_faces_under_threshold_clean():
    a = np.array([1.0, 0.05, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.10, 0.02, 0.0], dtype=np.float32)  # nearly collinear → small distance
    assert face_match.compare_embeddings({"a": a, "b": b}) == []


def test_single_or_no_face_is_no_op():
    # face_check no-ops without a backend; status is honest either way.
    findings, info = face_match.face_check({"only": "nonexistent.jpg"})
    assert findings == []
    st = face_match.status()
    assert "available" in st
