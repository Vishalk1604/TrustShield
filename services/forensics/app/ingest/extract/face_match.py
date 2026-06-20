"""Face-match across documents (plan §10 Phase 6) — is it the same person on every document?

A fraudster who pairs a genuine document with a *different* person's photo (or swaps the portrait on a
card) is caught by comparing the faces across the submitted documents: PAN photo vs Aadhaar photo vs a
selfie. We detect + embed each portrait and compare embeddings; a distance over threshold = different
people = identity-swap fraud → a HIGH semantic finding.

Behind a seam: needs a local face library — **insightface** (ArcFace, best) or **face_recognition**
(dlib, lighter). Both are optional (`requirements-models.txt`); the module no-ops gracefully if neither
is installed, so the rest of the pipeline is unaffected. Local-only; no network.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import numpy as np

# Cosine-distance threshold on (normalized) face embeddings: <= match, > different. ArcFace-calibrated;
# documented (project rule: no magic numbers). Conservative to avoid false "different person" flags.
FACE_MATCH_THRESHOLD = 0.62


@lru_cache(maxsize=1)
def _backend() -> Optional[str]:
    try:
        import insightface  # noqa: F401
        return "insightface"
    except Exception:
        pass
    try:
        import face_recognition  # noqa: F401
        return "face_recognition"
    except Exception:
        pass
    return None


def available() -> bool:
    return _backend() is not None


def status() -> dict:
    return {"available": available(), "backend": _backend(),
            "reason": None if available()
            else "no local face library — install insightface or face_recognition "
                 "(requirements-models.txt) to enable cross-document face matching"}


@lru_cache(maxsize=1)
def _insightface_app():  # pragma: no cover - requires the heavy lib + model
    import insightface
    app = insightface.app.FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def embed_face(image_path: str) -> Optional[np.ndarray]:
    """Return a face embedding for the dominant portrait in the image, or None. Never raises."""
    b = _backend()
    if not b:
        return None
    try:  # pragma: no cover - exercised only when a face lib is installed
        if b == "insightface":
            from PIL import Image
            faces = _insightface_app().get(np.asarray(Image.open(image_path).convert("RGB")))
            if not faces:
                return None
            faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
            return np.asarray(faces[0].normed_embedding, dtype=np.float32)
        import face_recognition
        img = face_recognition.load_image_file(image_path)
        encs = face_recognition.face_encodings(img)
        return np.asarray(encs[0], dtype=np.float32) if encs else None
    except Exception:
        return None


def _cos_dist(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(1.0 - np.dot(a, b))


def compare_embeddings(embeddings: dict) -> list[dict]:
    """`embeddings`: {label: vector}. Pairwise compare; a distance over threshold → HIGH 'face mismatch'
    finding. Pure logic — testable without any face library."""
    findings: list[dict] = []
    items = list(embeddings.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (la, ea), (lb, eb) = items[i], items[j]
            d = _cos_dist(ea, eb)
            if d > FACE_MATCH_THRESHOLD:
                findings.append({
                    "category": "semantic", "severity": "high",
                    "title": "Face mismatch across documents",
                    "description": (f"The photo on '{la}' does not match the photo on '{lb}' "
                                    f"(face distance {d:.2f} > {FACE_MATCH_THRESHOLD}). The documents "
                                    f"may belong to different people — a possible identity swap."),
                    "source_location": "face recognition (cross-document)",
                    "values": {"detector": "face_match", "distance": round(d, 3), "docs": [la, lb]},
                    "confidence": 0.75})
    return findings


def face_check(paths_by_label: dict) -> tuple[list[dict], dict]:
    """Embed each document's portrait + compare across them. (findings, info). No-op if unavailable."""
    if not available():
        return [], {"available": False}
    emb: dict = {}
    for label, path in paths_by_label.items():
        e = embed_face(path)
        if e is not None:
            emb[label] = e
    info = {"available": True, "backend": _backend(), "faces_found": len(emb)}
    if len(emb) < 2:
        return [], info
    return compare_embeddings(emb), info
