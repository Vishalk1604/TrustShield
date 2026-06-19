"""Local model-asset registry — the seam between heuristics (live) and trained models (later).

TrustShield ships and runs on heuristics. Large trained assets (LayoutLMv3, the DocTamper forgery
CNN, PaddleOCR weights) live under the repo `models/` directory (gitignored) and are loaded from
*local disk only* — never fetched over the network at runtime (the local-only contract).

This module is the single place that answers "is asset X available, and where?":

    from services.forensics.app.ingest.model_registry import model_available, resolve_model

    if model_available("layoutlmv3-base"):
        path = resolve_model("layoutlmv3-base")     # -> local Path
        ... load the model ...
    else:
        ... run the heuristic fallback (the default live path today) ...

Resolution order for the model store root:
  1. env `TRUSTSHIELD_MODEL_DIR` (if set)
  2. the repo-root `models/` directory (computed relative to this file)

An asset is "available" only when (a) the registry marks its status `present` AND (b) the path
actually exists on disk. This keeps the seam honest: deleting the binaries makes the heuristics take
over automatically, with no code change and no import of torch/transformers at runtime.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

# repo root = .../TrustShield  (this file is services/forensics/app/ingest/model_registry.py)
_REPO_ROOT = Path(__file__).resolve().parents[4]


def model_store_dir() -> Path:
    """Root directory of the local model store (env override, else repo `models/`)."""
    env = os.environ.get("TRUSTSHIELD_MODEL_DIR")
    if env:
        return Path(env).expanduser()
    return _REPO_ROOT / "models"


@lru_cache(maxsize=1)
def _load_registry() -> dict:
    """Read models/registry.json once. Missing/invalid file => empty registry (all fallbacks)."""
    path = model_store_dir() / "registry.json"
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"assets": []}


def _asset(name: str) -> Optional[dict]:
    for asset in _load_registry().get("assets", []):
        if asset.get("name") == name:
            return asset
    return None


def resolve_model(name: str) -> Optional[Path]:
    """Return the local Path to asset `name` if it is registered `present` AND exists on disk.

    Paths in registry.json are relative to the model store dir; entries may use `../` to point
    outside it (e.g. the FUNSD reference set under data/). Returns None otherwise — callers must
    then use their heuristic fallback.
    """
    asset = _asset(name)
    if not asset or asset.get("status") != "present":
        return None
    rel = asset.get("path")
    if not rel:
        return None
    path = (model_store_dir() / rel).resolve()
    return path if path.exists() else None


def model_available(name: str) -> bool:
    """True only if the asset resolves to an existing local path. Never raises, never networks."""
    return resolve_model(name) is not None


def asset_status(name: str) -> str:
    """'present' | 'absent' | 'unknown' (from the registry; does not check disk)."""
    asset = _asset(name)
    if asset is None:
        return "unknown"
    return str(asset.get("status", "unknown"))


def fallback_for(name: str) -> Optional[str]:
    """Human-readable description of the heuristic used when the asset is unavailable."""
    asset = _asset(name)
    return (asset or {}).get("fallback")
