"""Generalized forgery-localization model seam (plan §10 Phase 4).

A model-agnostic adapter over the heuristic baseline: a learned forgery-localization network (which
outputs a per-pixel tamper mask) localizes edits that the hand-tuned detectors miss — including
digital paint-overs and splices on documents. Backends:

  - **dtd**     — DocTamper DTD (delegates to `doctamper.py`); we train these weights ourselves on the
                  DocTamper dataset we hold (Phase 5), since the published checkpoint is gated.
  - **trufor**  — TruFor (public weights + reliability map); pretrained drop-in.
  - **catnet**  — CAT-Net (JPEG-compression-aware); pretrained drop-in.

Selected by `TRUSTSHIELD_FORGERY_BACKEND` (default `dtd`). **torch stays OPTIONAL** — nothing here
imports it unless a backend's weights are present locally. Inference for a non-DTD backend is provided
by a small vendored adapter `models/forgery/<backend>/code/trustshield_infer.py` (written by
`scripts/setup_forgery_model.py`) exposing `localize(image_path, weights_path) -> mask (HxW ndarray)`;
the seam turns that mask into bounding-box regions. Any failure → `None` → the heuristics stay live.
No network at runtime; everything loads from local disk.
"""

from __future__ import annotations

import importlib
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

from services.forensics.app.ingest import doctamper
from services.forensics.app.ingest.model_registry import model_store_dir

# Default is a no-op (no weights) → heuristics stay live. The `unet` backend (our own model trained on
# the DocTamper data) is OPT-IN via TRUSTSHIELD_FORGERY_BACKEND=unet: it's trained + integrated, but its
# cross-domain transfer to our document types is weak (the published-benchmark result — see DECISIONS),
# so it does not beat the heuristics on our docs and is not auto-enabled. Re-evaluate after fine-tuning
# on domain data (our synthetic + real Indian-doc tampered set with masks).
DEFAULT_BACKEND = "dtd"
BACKENDS = ("unet", "dtd", "trufor", "catnet")
MASK_THRESHOLD = 0.5       # binarize the model's tamper-probability mask
MIN_REGION_FRAC = 0.0008   # ignore connected components smaller than this fraction of the image


def backend_name() -> str:
    b = os.environ.get("TRUSTSHIELD_FORGERY_BACKEND", DEFAULT_BACKEND).lower().strip()
    return b if b in BACKENDS else DEFAULT_BACKEND


def _resolve_backend(backend: Optional[str]) -> str:
    """An explicit backend override (e.g. the live path requesting `unet`) or the env-selected default.
    Lets a caller pick a backend per-request without mutating os.environ (not thread-safe under uvicorn)."""
    if backend:
        b = backend.lower().strip()
        return b if b in BACKENDS else DEFAULT_BACKEND
    return backend_name()


def _backend_dir(backend: str) -> Path:
    return model_store_dir() / "forgery" / backend


def weights_path(backend: str) -> Optional[Path]:
    """Local checkpoint for a backend, or None. DTD reuses the doctamper seam's resolver."""
    if backend == "dtd":
        return doctamper.weights_path()
    d = _backend_dir(backend) / "weights"
    if d.exists():
        for pat in ("*.pth", "*.pt", "*.ckpt", "*.tar", "*.pth.tar"):
            hits = sorted(d.glob(pat))
            if hits:
                return hits[0]
    return None


@lru_cache(maxsize=1)
def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def available(backend: Optional[str] = None) -> bool:
    """True only if the (optionally overridden) backend can actually run (code + weights + torch, all local)."""
    b = _resolve_backend(backend)
    if b == "dtd":
        return doctamper.available()
    if b == "unet":  # our own model — inference lives in-repo (forgery_unet.py), no vendored adapter
        return weights_path("unet") is not None and _torch_available()
    return (weights_path(b) is not None
            and (_backend_dir(b) / "code" / "trustshield_infer.py").exists()
            and _torch_available())


def status(backend: Optional[str] = None) -> dict:
    """Transparent status surfaced in the analysis signals (so the UI/report is honest)."""
    b = _resolve_backend(backend)
    if b == "dtd":
        s = doctamper.status()
        s["backend"] = "dtd"
        return s
    if b == "unet":
        return {
            "backend": "unet",
            "available": available("unet"),
            "weights_present": weights_path("unet") is not None,
            "torch": _torch_available(),
            "reason": None if available("unet")
            else ("forgery U-Net not trained yet — run "
                  "`python services/forensics/train_forgery.py` (trains on the DocTamper data we hold; "
                  "writes models/forgery/unet/weights/forgery.pth, which this seam then auto-loads)"),
        }
    return {
        "backend": b,
        "available": available(b),
        "weights_present": weights_path(b) is not None,
        "adapter_present": (_backend_dir(b) / "code" / "trustshield_infer.py").exists(),
        "torch": _torch_available(),
        "reason": None if available(b)
        else (f"forgery model '{b}' not enabled — run `python scripts/setup_forgery_model.py {b}` "
              f"(downloads the repo + weights into models/forgery/{b}/ and installs torch)"),
    }


def localize(image_path: str, backend: Optional[str] = None) -> Optional[dict]:
    """Run the (optionally overridden) backend → {"regions": [(x0,y0,x1,y1), …], "mask_b64": str} or None.
    Never raises. `backend="unet"` lets the live path request our learned model regardless of the env default."""
    b = _resolve_backend(backend)
    if not available(b):
        return None
    try:
        if b == "dtd":
            return doctamper.localize(image_path)
        if b == "unet":
            from services.forensics.app.ingest import forgery_unet
            mask = forgery_unet.infer(image_path, str(weights_path("unet")))
            return mask_to_regions(mask, image_path) if mask is not None else None
        return _vendored_localize(b, image_path)
    except Exception:  # pragma: no cover - depends on local weights/torch
        return None


def _vendored_localize(backend: str, image_path: str) -> Optional[dict]:  # pragma: no cover
    """Load the vendored `trustshield_infer.py` for `backend`, run it → mask → regions."""
    code_dir = str(_backend_dir(backend) / "code")
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    infer = importlib.import_module("trustshield_infer")
    mask = infer.localize(image_path, str(weights_path(backend)))  # HxW float/bool array
    return mask_to_regions(mask, image_path)


def _calibration() -> dict:
    """Operating point chosen on the val split by the trainer (tau_mask + min_area_frac). Falls back to
    the module defaults when no calibration.json sits next to the unet weights."""
    wp = weights_path("unet")
    if wp is not None:
        cal_path = Path(wp).with_name("calibration.json")
        if cal_path.exists():
            try:
                import json
                return json.loads(cal_path.read_text())
            except Exception:
                pass
    return {"tau_mask": MASK_THRESHOLD, "min_area_frac": MIN_REGION_FRAC}


def mask_to_regions(mask, image_path: str) -> Optional[dict]:
    """Convert a model tamper-probability mask (HxW, the model's resolution) into image-space bounding
    boxes + a base64 overlay-ready mask PNG. Pure numpy/PIL/cv2 (no torch). Returns None if empty.
    Thresholds (tau_mask, min_area_frac) come from the val-calibrated `calibration.json` when present."""
    import base64
    import io

    import numpy as np
    from PIL import Image

    cal = _calibration()
    tau_mask = float(cal.get("tau_mask", MASK_THRESHOLD))
    min_area_frac = float(cal.get("min_area_frac", MIN_REGION_FRAC))

    arr = np.asarray(mask, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr.mean(axis=2)
    if arr.size == 0:
        return None
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    binm = (arr >= tau_mask).astype(np.uint8)
    # upscale the mask to the original image size
    if binm.shape != (H, W):
        binm = np.asarray(Image.fromarray(binm * 255).resize((W, H), Image.NEAREST)) > 127
        binm = binm.astype(np.uint8)
    if int(binm.sum()) == 0:
        return None

    regions: list[tuple[int, int, int, int]] = []
    min_area = min_area_frac * W * H
    try:
        import cv2
        n, _, stats, _ = cv2.connectedComponentsWithStats(binm, connectivity=8)
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area >= min_area:
                regions.append((int(x), int(y), int(x + w), int(y + h)))
    except Exception:
        ys, xs = np.where(binm > 0)  # fallback: single bounding box
        if len(xs):
            regions.append((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())))
    if not regions:
        return None

    buf = io.BytesIO()
    Image.fromarray(binm * 255).save(buf, "PNG")
    return {"regions": regions, "mask_b64": base64.b64encode(buf.getvalue()).decode("ascii")}
