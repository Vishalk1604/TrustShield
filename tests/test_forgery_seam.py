"""Generalized forgery-localization model seam (plan §10 Phase 4).

With no weights/torch present the seam must be a clean no-op (heuristics stay live); the mask→regions
conversion (pure numpy/PIL/cv2, used once a model IS present) is tested directly on a synthetic mask.
"""

import numpy as np
from PIL import Image

from services.forensics.app.ingest import forgery_model


def test_backend_selection_default_unet(monkeypatch):
    monkeypatch.delenv("TRUSTSHIELD_FORGERY_BACKEND", raising=False)
    assert forgery_model.backend_name() == "unet"        # our own trainable model is the default
    monkeypatch.setenv("TRUSTSHIELD_FORGERY_BACKEND", "trufor")
    assert forgery_model.backend_name() == "trufor"
    monkeypatch.setenv("TRUSTSHIELD_FORGERY_BACKEND", "bogus")  # unknown → default
    assert forgery_model.backend_name() == "unet"


def test_unet_backend_unavailable_without_weights(monkeypatch):
    # Default backend, but no trained weights yet → heuristics stay live, status is honest.
    monkeypatch.delenv("TRUSTSHIELD_FORGERY_BACKEND", raising=False)
    st = forgery_model.status()
    assert st["backend"] == "unet" and st["available"] is False and st["reason"]
    assert forgery_model.localize("nonexistent.png") is None


def test_seam_unavailable_without_weights(monkeypatch):
    # No weights placed → no backend can run → heuristics stay live.
    monkeypatch.setenv("TRUSTSHIELD_FORGERY_BACKEND", "trufor")
    assert forgery_model.available() is False
    assert forgery_model.localize("nonexistent.png") is None
    st = forgery_model.status()
    assert st["backend"] == "trufor" and st["available"] is False and st["reason"]


def test_dtd_backend_delegates_to_doctamper(monkeypatch):
    monkeypatch.setenv("TRUSTSHIELD_FORGERY_BACKEND", "dtd")
    st = forgery_model.status()
    assert st["backend"] == "dtd" and "available" in st        # delegated doctamper status


def test_mask_to_regions_from_synthetic_mask(tmp_path):
    p = tmp_path / "img.png"
    Image.new("RGB", (200, 160), (230, 230, 230)).save(p)
    mask = np.zeros((160, 200), dtype=np.float32)
    mask[40:90, 60:140] = 1.0                                   # one tampered blob
    out = forgery_model.mask_to_regions(mask, str(p))
    assert out and out["regions"]
    x0, y0, x1, y1 = out["regions"][0]
    assert x0 <= 70 <= x1 and y0 <= 60 <= y1                    # box covers the blob
    assert out["mask_b64"]


def test_mask_to_regions_empty_is_none(tmp_path):
    p = tmp_path / "img.png"
    Image.new("RGB", (120, 120), (255, 255, 255)).save(p)
    assert forgery_model.mask_to_regions(np.zeros((120, 120), np.float32), str(p)) is None
