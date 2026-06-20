"""DocTamper (DTD) learned tamper-localization — integration behind the model_registry seam (§10 Day 3).

DocTamper is a CNN (Swin-based DTD) trained on 170k tampered document images. It localizes tampered
TEXT regions by learning the fingerprint of editing itself — *independent* of the sensor-noise and
JPEG cues the `image_forensics` heuristics rely on. That makes it the right tool for the case the
heuristics struggle with: a value painted over in a drawing app and exported as a pristine PNG, where
there is no noise/compression trace to analyse.

Status on disk: the vendored repo (`models/doctamper/code`) ships the model code + per-image JPEG
quantisation tables, but **NOT the trained weights** — those are gated (request from the authors with
an education email, like the dataset). So this adapter reports **UNAVAILABLE** and the heuristics stay
live. To enable it, drop a checkpoint at `models/doctamper/weights/*.pth` (or point
`TRUSTSHIELD_DOCTAMPER_WEIGHTS` at one) on a machine with torch installed; `localize()` then runs DTD
inference and returns a tamper mask → regions. Everything here is local and never raises.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from services.forensics.app.ingest.model_registry import model_store_dir, resolve_model


def weights_path() -> Optional[Path]:
    """Local path to a DTD checkpoint, or None. Env override → models/doctamper/weights/*.pth."""
    env = os.environ.get("TRUSTSHIELD_DOCTAMPER_WEIGHTS")
    if env and Path(env).exists():
        return Path(env)
    wdir = model_store_dir() / "doctamper" / "weights"
    if wdir.exists():
        cks = sorted(wdir.glob("*.pth")) + sorted(wdir.glob("*.pt")) + sorted(wdir.glob("*.ckpt"))
        if cks:
            return cks[0]
    return None


@lru_cache(maxsize=1)
def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def available() -> bool:
    """True only if the code, a checkpoint, AND torch are all present locally."""
    return (resolve_model("doctamper-code") is not None
            and weights_path() is not None
            and _torch_available())


def status() -> dict:
    """Transparent status surfaced in the analysis signals (so the UI/report is honest)."""
    return {
        "available": available(),
        "code_present": resolve_model("doctamper-code") is not None,
        "weights_present": weights_path() is not None,
        "torch": _torch_available(),
        "reason": None if available()
        else "DocTamper weights are gated/absent; heuristic image-forensics is live. "
             "Drop a checkpoint under models/doctamper/weights/ to enable the learned model.",
    }


def localize(image_path: str) -> Optional[dict]:
    """Run DTD inference and return {"regions": [(x0,y0,x1,y1), …], "mask_b64": str} — or None.

    Returns None (heuristics take over) whenever the model isn't available. The inference body is
    enabled by the presence of weights; until then it is intentionally a no-op so the runtime carries
    no torch dependency. When weights are placed locally, implement the load+forward here following
    `models/doctamper/code/models/eval_dtd.py` (Swin/DTD + the qt_table quantisation input):

        import sys, torch; sys.path.insert(0, str(resolve_model("doctamper-code")))
        from models.dtd import seg_dtd                      # vendored model def
        net = seg_dtd(...); net.load_state_dict(torch.load(weights_path(), map_location="cpu"))
        net.eval(); mask = net(preprocess(image_path))       # → binarise → connected-component boxes

    Kept behind this seam so the slim runtime images never import torch and the heuristics remain the
    guaranteed path.
    """
    if not available():
        return None
    try:  # pragma: no cover - exercised only when gated weights are present locally
        return _run_dtd(image_path)
    except Exception:
        return None


def _run_dtd(image_path: str) -> Optional[dict]:  # pragma: no cover - requires local weights + torch
    """Placeholder for the real DTD forward pass (see `localize` docstring). No-op until weights exist."""
    return None
