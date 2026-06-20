"""Recapture / rescreen detection (plan §10) — is this a photo of a SCREEN or a HALFTONE copy?

A genuine scan or photo of a paper document has a smooth, monotonically-decaying Fourier spectrum.
A **photo of an LCD/LED screen** (the display's pixel grid) or a **halftone photocopy / reprint** (the
print screen) imposes a regular periodic micro-pattern, which shows up as a few **sharp, isolated
high-frequency peaks** in the 2-D FFT. Detecting those peaks flags a document that was re-captured from a
screen or re-screened — a strong "this isn't an original" signal, orthogonal to the pixel-edit detectors.

CPU-only (numpy + Pillow), conservative by design (multiple very-strong high-frequency peaks required),
so original scans/photos and clean renders do NOT fire. Reported MEDIUM (a risk signal, not proof).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# ── documented constants ────────────────────────────────────────────────────────
RC_MAX_DIM = 1024          # downscale long side before the FFT (speed; periodicity survives)
RC_HIGH_FREQ_FRAC = 0.34   # only consider peaks beyond this fraction of Nyquist — a screen pixel
                           # grid / halftone sits HIGH; text-line periodicity sits low (excluded)
# Documents are confounders: text edges (broadband) + the JPEG 8x8 block grid both create high-freq
# peaks (~30-37 dB above the band median in our real/synthetic docs). A genuine screen/halftone grid
# is a near-pure tone (~50 dB). So the bar is set well above the document confounders, and several such
# peaks are required — conservative on purpose (miss a subtle recapture rather than false-flag a scan).
RC_PEAK_PROMINENCE = 44.0  # a peak must exceed the band's median by this many dB (log-magnitude)
RC_MIN_PEAKS = 4           # min strong high-freq peaks to call it a recapture (grids give symmetric sets)
RC_PEAKS_FULL = 12         # peak count mapping to strength 1.0
RC_MAX_PEAKS_SCAN = 28     # NMS budget
RC_AXIS_STRIP_FRAC = 0.06  # exclude a strip around the kx/ky axes: a screen pixel grid is a 2-D
                           # LATTICE (off-axis peaks), whereas repeated text/lines are 1-D periodicity
                           # ON an axis — excluding the axes rejects that confounder


def _count_prominent_peaks(mag: np.ndarray, band: np.ndarray) -> tuple[int, float]:
    """Count sharp local-maxima peaks in the high-frequency `band` that exceed the band median by
    RC_PEAK_PROMINENCE dB. Non-maximum suppression with a small exclusion window per peak."""
    base = float(np.median(mag[band]))
    work = np.where(band, mag, -np.inf)
    h, w = mag.shape
    ry, rx = max(3, h // 40), max(3, w // 40)
    peaks = 0
    for _ in range(RC_MAX_PEAKS_SCAN):
        idx = int(np.argmax(work))
        y, x = divmod(idx, w)
        if not np.isfinite(work[y, x]) or (work[y, x] - base) < RC_PEAK_PROMINENCE:
            break
        peaks += 1
        work[max(0, y - ry):y + ry + 1, max(0, x - rx):x + rx + 1] = -np.inf
    return peaks, base


def detect_recapture(img: Image.Image) -> dict:
    """Return {is_recapture, peaks, strength, prominence_db}. Never raises."""
    gray = img.convert("L")
    w, h = gray.size
    if max(w, h) > RC_MAX_DIM:
        s = RC_MAX_DIM / float(max(w, h))
        gray = gray.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)
    a = np.asarray(gray, dtype=np.float32)
    if a.shape[0] < 64 or a.shape[1] < 64:
        return {"is_recapture": False, "peaks": 0, "strength": 0.0, "prominence_db": 0.0}

    # Hann window (kill edge-leakage cross artifacts) → 2-D FFT log-magnitude.
    a = a - float(a.mean())
    a = a * np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    mag = 20.0 * np.log10(np.abs(np.fft.fftshift(np.fft.fft2(a))) + 1e-6)

    cy, cx = np.array(mag.shape) // 2
    yy, xx = np.ogrid[: mag.shape[0], : mag.shape[1]]
    radius = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    # high-frequency annulus AND off both axes (reject 1-D text/line periodicity; keep 2-D grids)
    strip_y = RC_AXIS_STRIP_FRAC * mag.shape[0]
    strip_x = RC_AXIS_STRIP_FRAC * mag.shape[1]
    off_axis = (np.abs(yy - cy) > strip_y) & (np.abs(xx - cx) > strip_x)
    band = (radius > (RC_HIGH_FREQ_FRAC * float(radius.max()))) & off_axis

    peaks, base = _count_prominent_peaks(mag, band)
    peak_db = (float(np.max(mag[band])) - base) if band.any() else 0.0
    return {
        "is_recapture": peaks >= RC_MIN_PEAKS,
        "peaks": int(peaks),
        "strength": round(min(1.0, peaks / float(RC_PEAKS_FULL)), 3),
        "prominence_db": round(peak_db, 1),
    }


def recapture_finding(img: Image.Image) -> tuple[list[dict], dict]:
    """Run recapture detection → (findings, signal). Image-level (no bbox); MEDIUM severity."""
    try:
        sig = detect_recapture(img)
    except Exception as exc:  # pragma: no cover
        return [], {"error": str(exc)}
    findings: list[dict] = []
    if sig["is_recapture"]:
        findings.append({
            "category": "forensic",
            "severity": "medium",
            "title": "Possible screen recapture / rescreen",
            "description": (
                "The image carries a strong regular high-frequency pattern — the fingerprint of a "
                "photo taken OF A SCREEN, or a halftone photocopy/reprint, rather than an original "
                f"scan of paper ({sig['peaks']} sharp grid peaks). Genuine document scans/photos do "
                "not show this. Treat the document as a re-captured copy."),
            "source_location": "recapture analysis (FFT periodicity)",
            "values": {"detector": "recapture", "peaks": sig["peaks"],
                       "prominence_db": sig["prominence_db"], "strength": sig["strength"]},
            "confidence": 0.6,
        })
    return findings, sig
