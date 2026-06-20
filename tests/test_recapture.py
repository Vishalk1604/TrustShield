"""Recapture / rescreen detection (plan §10 Phase 2).

A genuine document scan/photo has a smooth spectrum; a photo of a SCREEN or a halftone copy imposes a
strong periodic grid → sharp high-frequency FFT peaks. The detector must FIRE on a screen-grid image and
stay SILENT on normal documents (text edges + JPEG block grid are confounders we must not flag).
"""

import io

import numpy as np
import pytest
from PIL import Image

from services.forensics.app.recapture import detect_recapture, recapture_finding


def _doc(seed: int = 0) -> Image.Image:
    """A normal 'document photo': paper + text bars + mild sensor noise, saved through JPEG."""
    rng = np.random.default_rng(seed)
    a = np.full((360, 520), 224, dtype=np.float32)
    for y in range(40, 330, 42):
        a[y:y + 7, 40:470] = 35
    a += rng.normal(0, 6, a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGB")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=90); buf.seek(0)
    return Image.open(buf).convert("RGB")


def _screen_grid(img: Image.Image, pitch: float = 3.0, amp: float = 0.25) -> Image.Image:
    """Impose an LCD-style pixel grid (strong periodic modulation) → a 'photo of a screen'."""
    a = np.asarray(img.convert("L"), dtype=np.float32)
    h, w = a.shape
    yy, xx = np.mgrid[:h, :w]
    grid = 1.0 + amp * np.cos(2 * np.pi * xx / pitch) * np.cos(2 * np.pi * yy / pitch)
    return Image.fromarray(np.clip(a * grid, 0, 255).astype(np.uint8)).convert("RGB")


def test_normal_document_is_not_recapture():
    for seed in (0, 1, 2):
        sig = detect_recapture(_doc(seed))
        assert sig["is_recapture"] is False, sig
        findings, _ = recapture_finding(_doc(seed))
        assert findings == []


def test_screen_grid_is_flagged():
    grid = _screen_grid(_doc(0), pitch=3.0, amp=0.25)
    sig = detect_recapture(grid)
    assert sig["is_recapture"] is True and sig["peaks"] >= 4
    findings, _ = recapture_finding(grid)
    assert findings and findings[0]["severity"] == "medium"
    assert findings[0]["values"]["detector"] == "recapture"


@pytest.mark.parametrize("pitch,amp", [(2.5, 0.30), (4.0, 0.20)])
def test_screen_grid_various_pitches(pitch, amp):
    assert detect_recapture(_screen_grid(_doc(1), pitch, amp))["is_recapture"] is True


def test_tiny_image_is_safe():
    sig = detect_recapture(Image.new("RGB", (20, 20), (128, 128, 128)))
    assert sig["is_recapture"] is False
