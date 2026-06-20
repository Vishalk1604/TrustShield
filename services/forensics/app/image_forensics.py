"""Image / pixel forensics — detect & localize edits in raster documents (plan §6.D1, §10).

The §6.D2/D3 forensics catch edits in a PDF's *text layer*. This module catches edits in the
*pixels* — exactly the case the hackathon judges asked about: a scanned or photographed document
whose number/photo was altered in an image editor, where there is no text layer to compare against.

It runs the standard image-forensics toolkit, all local CPU, and returns both machine-readable
findings (with bounding boxes, in the same shape the rest of the pipeline uses) and an annotated
overlay image showing *where* the edit is:

  1. ELA (Error-Level Analysis) — recompress at a known JPEG quality and diff; spliced/edited
     regions sit at a different error level than the rest of the page.
  2. Noise-residual inconsistency — pasted content carries different sensor/scan noise; a local
     high-pass residual exposes blocks whose noise deviates from the document's baseline.
  3. Copy-move (clone) detection — ORB keypoints + consistent-offset clustering, then verified by
     normalized cross-correlation on the actual pixels (so repeated glyphs don't false-trigger).
  4. JPEG-ghost — recompress across a quality sweep; a region that "bottoms out" at a different
     quality than the page was likely recompressed/spliced. (Conservative — corroboration only.)
  5. EXIF / software trace — editor software in the metadata (Photoshop/GIMP/…), modify-after-create.

Design principles (so a clean document does NOT light up):
  - Robust statistics: thresholds use the median + k·MAD (not mean/std), which tolerate the heavy
    tails of real scans.
  - Coherent clusters only: isolated single-block hits are dropped; a finding needs a contiguous
    region.
  - Corroboration: two pixel-level detectors agreeing on the same area escalates; a lone weak
    signal stays low. Copy-move must pass a pixel NCC check; EXIF software is a strong standalone.

Everything degrades gracefully: missing cv2 disables only copy-move; any detector that raises is
skipped, never sinking the analysis. No network, ever.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

try:
    from PIL.ExifTags import TAGS as _EXIF_TAGS
except Exception:  # pragma: no cover
    _EXIF_TAGS = {}

try:
    import cv2  # opencv-python-headless

    _CV2 = True
except Exception:  # pragma: no cover - cv2 optional; copy-move degrades to skipped
    _CV2 = False


# ── documented constants (project rule: no magic numbers) ────────────────────────
ELA_QUALITY = 90           # recompression quality for Error-Level Analysis
BLOCK = 16                 # px block size for ELA / noise block statistics
MAD_K = 6.0                # robust threshold = median + MAD_K · 1.4826 · MAD
ELA_ABS_FLOOR = 14.0       # min mean block ELA energy (0–255) to consider at all
ELA_MIN_BLOCKS = 3         # min contiguous flagged blocks to form an ELA region
# Noise is estimated on FLAT (non-text) pixels so text edges aren't mistaken for noise; a tampered
# region (painted/pasted/recompressed) loses the page's sensor-noise floor → its block noise drops.
NOISE_FLAT_GRAD = 6.0      # local gradient below this = a flat (non-edge) pixel
NOISE_MIN_FLAT_FRAC = 0.22 # a block needs this fraction of flat pixels to get a noise estimate
NOISE_MIN_FLOOR = 2.2      # page noise σ below this = too clean to detect a "lost noise" edit
NOISE_LOW_FRAC = 0.50      # a block whose noise is < 50% of the page floor is suspicious
NOISE_MIN_BLOCKS = 5       # min contiguous low-noise blocks to form a region
COPYMOVE_FEATURES = 5000   # ORB keypoint budget
COPYMOVE_MIN_OFFSET = 30   # px; ignore matches within the same neighbourhood
COPYMOVE_MIN_MATCHES = 10  # min consistent-offset matches to call a clone
COPYMOVE_NCC = 0.92        # CONTENT cross-correlation of the two patches
COPYMOVE_NOISE_NCC = 0.30  # NOISE-residual correlation: a literal copy duplicates the sensor noise,
                           # whereas independently-scanned repeated glyphs do not — the key gate
COPYMOVE_MAX_CLUSTER_FRAC = 0.06  # src/dst keypoint clusters must be COMPACT (rejects repeated text)
JPEG_GHOST_QUALITIES = (55, 65, 75, 85, 95)
MAX_DIM = 2000             # downscale very large uploads before analysis (speed; px on long side)

# Editor software substrings that should never appear on a genuine bank/govt document scan.
EDITOR_SOFTWARE = (
    "photoshop", "gimp", "paint.net", "ms paint", "snapseed", "lightroom", "pixelmator",
    "affinity", "canva", "inkscape", "imagemagick", "picsart", "photopea", "acdsee", "corel",
    "skitch", "photoscape", "fotor", "luminar", "facetune",
)


@dataclass
class Region:
    bbox: tuple[int, int, int, int]   # (x0, y0, x1, y1) in pixels
    detector: str
    strength: float                   # 0–1


def _b64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _load_rgb(path: str) -> tuple[Image.Image, str]:
    """Open as RGB, downscaling huge uploads. Returns (image, original_format)."""
    img = Image.open(path)
    fmt = (img.format or "").upper()
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_DIM:
        scale = MAX_DIM / float(max(w, h))
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    return img, fmt


# ── robust block helpers ──────────────────────────────────────────────────────────

def _block_grid(energy: np.ndarray, block: int = BLOCK) -> np.ndarray:
    """Mean of `energy` over a non-overlapping block grid → (gh, gw)."""
    h, w = energy.shape
    gh, gw = h // block, w // block
    if gh == 0 or gw == 0:
        return np.zeros((0, 0), dtype=np.float32)
    e = energy[: gh * block, : gw * block]
    return e.reshape(gh, block, gw, block).mean(axis=(1, 3))


def _robust_threshold(values: np.ndarray) -> float:
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med))) + 1e-6
    return med + MAD_K * 1.4826 * mad


def _components(mask: np.ndarray, min_blocks: int) -> list[list[tuple[int, int]]]:
    """4-connected components over a small boolean block grid (pure numpy BFS)."""
    gh, gw = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps: list[list[tuple[int, int]]] = []
    for i in range(gh):
        for j in range(gw):
            if mask[i, j] and not seen[i, j]:
                stack = [(i, j)]
                seen[i, j] = True
                cells: list[tuple[int, int]] = []
                while stack:
                    y, x = stack.pop()
                    cells.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < gh and 0 <= nx < gw and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                if len(cells) >= min_blocks:
                    comps.append(cells)
    return comps


def _cells_to_bbox(cells: list[tuple[int, int]], block: int = BLOCK) -> tuple[int, int, int, int]:
    ys = [c[0] for c in cells]
    xs = [c[1] for c in cells]
    return (min(xs) * block, min(ys) * block, (max(xs) + 1) * block, (max(ys) + 1) * block)


# ── 1. ELA ──────────────────────────────────────────────────────────────────────

def _ela_energy(img: Image.Image) -> np.ndarray:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=ELA_QUALITY)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")
    diff = ImageChops.difference(img, recompressed)
    return np.asarray(diff, dtype=np.float32).max(axis=2)  # per-pixel max-channel energy


def _ela_regions(energy: np.ndarray) -> tuple[list[Region], np.ndarray]:
    bm = _block_grid(energy)
    if bm.size == 0:
        return [], bm
    thr = max(_robust_threshold(bm), ELA_ABS_FLOOR)
    mask = bm > thr
    regions: list[Region] = []
    span = float(bm.max() - thr) or 1.0
    for cells in _components(mask, ELA_MIN_BLOCKS):
        region_mean = float(np.mean([bm[y, x] for y, x in cells]))
        strength = max(0.0, min(1.0, (region_mean - thr) / span))
        regions.append(Region(_cells_to_bbox(cells), "ela", round(strength, 3)))
    return regions, bm


# ── 2. noise inconsistency (flat-pixel sensor-noise estimate) ────────────────────────

def _block_noise_sigma(img: Image.Image) -> np.ndarray:
    """Per-block sensor-noise σ estimated over FLAT (non-edge) pixels only.

    Text/line edges produce a huge high-pass residual that has nothing to do with sensor noise,
    so naively flagging "high-residual" blocks lights up every line of text. Instead we high-pass
    the image, keep only low-gradient (flat) pixels, and take their residual std per block — a
    genuine estimate of the local noise floor. Blocks without enough flat pixels return NaN.
    """
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    blur = np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(1.0)), dtype=np.float32)
    residual = gray - blur
    gyy, gxx = np.gradient(blur)
    flat = np.hypot(gxx, gyy) < NOISE_FLAT_GRAD

    h, w = gray.shape
    gh, gw = h // BLOCK, w // BLOCK
    sigma = np.full((gh, gw), np.nan, dtype=np.float32)
    need = int(NOISE_MIN_FLAT_FRAC * BLOCK * BLOCK)
    for i in range(gh):
        for j in range(gw):
            ys, xs = i * BLOCK, j * BLOCK
            fblk = flat[ys:ys + BLOCK, xs:xs + BLOCK]
            if int(fblk.sum()) >= need:
                sigma[i, j] = residual[ys:ys + BLOCK, xs:xs + BLOCK][fblk].std()
    return sigma


def _noise_regions(img: Image.Image) -> list[Region]:
    sigma = _block_noise_sigma(img)
    valid = ~np.isnan(sigma)
    if int(valid.sum()) < 8:
        return []
    g = float(np.median(sigma[valid]))
    if g < NOISE_MIN_FLOOR:  # essentially noise-free (pure digital render) → can't detect lost noise
        return []
    low_thr = g * NOISE_LOW_FRAC                    # blocks well below the page's noise floor
    mask = valid & (sigma < low_thr)
    regions: list[Region] = []
    span = float(low_thr) or 1.0
    for cells in _components(mask, NOISE_MIN_BLOCKS):
        region_sigma = float(np.mean([sigma[y, x] for y, x in cells]))
        strength = max(0.0, min(1.0, (low_thr - region_sigma) / span))
        regions.append(Region(_cells_to_bbox(cells), "noise", round(strength, 3)))
    return regions


# ── 3. copy-move (clone) — cv2 only ─────────────────────────────────────────────────

def _copy_move_regions(img: Image.Image) -> list[Region]:
    if not _CV2:
        return []
    gray = np.asarray(img.convert("L"))
    orb = cv2.ORB_create(nfeatures=COPYMOVE_FEATURES)
    kps, desc = orb.detectAndCompute(gray, None)
    if desc is None or len(kps) < 2 * COPYMOVE_MIN_MATCHES:
        return []
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = bf.knnMatch(desc, desc, k=4)  # k>1; self-match is excluded below

    # Collect candidate clone pairs: spatially distant, low descriptor distance.
    offset_bins: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}
    for matches in knn:
        for m in matches:
            if m.queryIdx == m.trainIdx:
                continue
            p1 = kps[m.queryIdx].pt
            p2 = kps[m.trainIdx].pt
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            if (dx * dx + dy * dy) ** 0.5 < COPYMOVE_MIN_OFFSET:
                continue
            key = (int(round(dx / 8.0)), int(round(dy / 8.0)))  # quantise the translation
            offset_bins.setdefault(key, []).append(
                (int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))
            )

    img_area = float(gray.shape[0] * gray.shape[1])
    regions: list[Region] = []
    for pairs in offset_bins.values():
        if len(pairs) < COPYMOVE_MIN_MATCHES:
            continue
        verified = [p for p in pairs if _ncc_ok(gray, p)]
        if len(verified) < COPYMOVE_MIN_MATCHES:
            continue
        # Compactness gate: a real clone moves a CONTIGUOUS region, so the source keypoints form a
        # tight cluster and so do the destinations. Repeated body text produces the same dominant
        # offset but with points scattered across the whole page — reject those (large clusters).
        sx = [p[0] for p in verified]; sy = [p[1] for p in verified]
        dx_ = [p[2] for p in verified]; dy_ = [p[3] for p in verified]
        src_area = (max(sx) - min(sx)) * (max(sy) - min(sy))
        dst_area = (max(dx_) - min(dx_)) * (max(dy_) - min(dy_))
        if src_area > COPYMOVE_MAX_CLUSTER_FRAC * img_area or \
           dst_area > COPYMOVE_MAX_CLUSTER_FRAC * img_area:
            continue
        bbox = (min(dx_) - BLOCK, min(dy_) - BLOCK, max(dx_) + BLOCK, max(dy_) + BLOCK)
        strength = min(1.0, len(verified) / float(3 * COPYMOVE_MIN_MATCHES))
        regions.append(Region(_clamp_bbox(bbox, gray.shape), "copy_move", round(strength, 3)))
    return regions


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = (np.sqrt((a * a).sum()) * np.sqrt((b * b).sum())) + 1e-6
    return float((a * b).sum() / denom)


def _ncc_ok(gray: np.ndarray, pair: tuple[int, int, int, int], win: int = 12) -> bool:
    """Confirm a clone candidate. A true copy-move duplicates pixels *and the sensor noise*, so we
    require BOTH the content AND the high-pass noise residual of the two patches to correlate.
    Repeated-but-independently-scanned glyphs match on content but NOT on noise → rejected."""
    x1, y1, x2, y2 = pair
    h, w = gray.shape
    if not (win <= x1 < w - win and win <= y1 < h - win and win <= x2 < w - win and win <= y2 < h - win):
        return False
    a = gray[y1 - win:y1 + win, x1 - win:x1 + win].astype(np.float32)
    b = gray[y2 - win:y2 + win, x2 - win:x2 + win].astype(np.float32)
    if _ncc(a, b) < COPYMOVE_NCC:
        return False
    if _CV2:
        # Isolate sensor NOISE with an edge-preserving (bilateral) filter: residual = image minus
        # its edge-preserved denoise ≈ noise only (text edges cancel). A literal pixel copy shares
        # this noise (high NCC); independently-scanned repeated glyphs do not (low NCC).
        ra = a - cv2.bilateralFilter(a, 5, 40, 5)
        rb = b - cv2.bilateralFilter(b, 5, 40, 5)
        return _ncc(ra, rb) >= COPYMOVE_NOISE_NCC
    return True


def _clamp_bbox(b, shape) -> tuple[int, int, int, int]:
    h, w = shape
    return (max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3]))


# ── 4. JPEG ghost (conservative corroboration) ──────────────────────────────────────

def _jpeg_ghost_regions(img: Image.Image) -> list[Region]:
    base = np.asarray(img, dtype=np.float32)
    best_q = None
    best_diff = None
    for q in JPEG_GHOST_QUALITIES:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q)
        buf.seek(0)
        rec = np.asarray(Image.open(buf).convert("RGB"), dtype=np.float32)
        diff = np.abs(base - rec).mean(axis=2)
        bm = _block_grid(diff)
        if best_diff is None:
            best_diff = np.full_like(bm, np.inf)
            best_q = np.zeros_like(bm)
        better = bm < best_diff
        best_q[better] = q
        best_diff[better] = bm[better]
    if best_q is None or best_q.size == 0:
        return []
    mode = float(np.median(best_q))
    # Regions whose recompression "ghost" bottoms out far from the page's dominant quality.
    mask = np.abs(best_q - mode) >= 20.0
    regions: list[Region] = []
    for cells in _components(mask, ELA_MIN_BLOCKS):
        regions.append(Region(_cells_to_bbox(cells), "jpeg_ghost", 0.4))
    return regions


# ── 5. EXIF / software trace ─────────────────────────────────────────────────────────

def _exif_findings(img: Image.Image) -> list[dict]:
    findings: list[dict] = []
    try:
        exif = img.getexif()
    except Exception:
        exif = None
    if not exif:
        return findings
    tags = {_EXIF_TAGS.get(k, k): v for k, v in exif.items()}
    software = str(tags.get("Software", "")).lower()
    hit = next((s for s in EDITOR_SOFTWARE if s in software), None)
    if hit:
        findings.append(_finding(
            "high", "Image-editor software in metadata",
            f"The image's EXIF 'Software' tag is '{tags.get('Software')}', i.e. it was last written "
            f"by an image editor ({hit}). Genuine bank/government document scans are not saved by "
            f"photo-editing tools — a strong sign the file was opened and re-exported after editing.",
            {"software": str(tags.get("Software"))}, confidence=0.9,
        ))
    dt = str(tags.get("DateTime", ""))
    dto = str(tags.get("DateTimeOriginal", ""))
    if dt and dto and dt != dto:
        findings.append(_finding(
            "low", "Modified after capture (EXIF)",
            f"The EXIF modify time ({dt}) differs from the original capture time ({dto}); the file "
            f"was re-saved after it was created.",
            {"DateTime": dt, "DateTimeOriginal": dto}, confidence=0.6,
        ))
    return findings


# ── finding helpers + aggregation ───────────────────────────────────────────────────

def _finding(severity: str, title: str, description: str, values: dict,
             confidence: float = 0.8, regions: Optional[list] = None) -> dict:
    v = dict(values)
    if regions:
        v["regions"] = [{"page": 1, "bbox": list(map(int, r))} for r in regions]
    return {
        "category": "forensic",
        "severity": severity,
        "title": title,
        "description": description,
        "source_location": "image forensics",
        "values": v,
        "confidence": round(confidence, 3),
    }


def _overlap(a: tuple, b: tuple) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _severity_for(strength: float) -> str:
    if strength >= 0.66:
        return "high"
    if strength >= 0.33:
        return "medium"
    return "low"


SEVERITY_COLOR = {"critical": (220, 38, 38), "high": (239, 68, 68), "medium": (234, 179, 8),
                  "low": (56, 189, 248), "info": (100, 116, 139)}


def analyze_image(path: str) -> dict:
    """Run the full image-forensics suite on one raster image.

    Returns a dict with `ok`, image dimensions, EvidenceItem-shaped `findings` (forensic
    category, each with `values.regions` boxes), an `annotated_b64` overlay + an `ela_b64`
    heatmap, raw per-detector `signals`, and a 0–100 `image_trust` / verdict. Never raises.
    """
    try:
        img, fmt = _load_rgb(path)
    except Exception as exc:
        return {"ok": False, "error": f"could not open image: {exc}", "findings": []}

    w, h = img.size
    findings: list[dict] = []
    signals: dict = {"format": fmt, "cv2": _CV2}

    # Detectors (each guarded — one failure never sinks the analysis).
    ela_regions: list[Region] = []
    ela_bm = np.zeros((0, 0), dtype=np.float32)
    try:
        energy = _ela_energy(img)
        ela_regions, ela_bm = _ela_regions(energy)
        signals["ela"] = {"regions": len(ela_regions),
                          "max_block": round(float(ela_bm.max()), 2) if ela_bm.size else 0.0}
    except Exception as exc:  # pragma: no cover
        signals["ela_error"] = str(exc)
        energy = None

    noise_regions: list[Region] = []
    try:
        noise_regions = _noise_regions(img)
        signals["noise"] = {"regions": len(noise_regions)}
    except Exception as exc:  # pragma: no cover
        signals["noise_error"] = str(exc)

    cm_regions: list[Region] = []
    try:
        cm_regions = _copy_move_regions(img)
        signals["copy_move"] = {"regions": len(cm_regions), "available": _CV2}
    except Exception as exc:  # pragma: no cover
        signals["copy_move_error"] = str(exc)

    ghost_regions: list[Region] = []
    try:
        ghost_regions = _jpeg_ghost_regions(img)
        signals["jpeg_ghost"] = {"regions": len(ghost_regions)}
    except Exception as exc:  # pragma: no cover
        signals["jpeg_ghost_error"] = str(exc)

    exif_findings = []
    try:
        exif_findings = _exif_findings(img)
    except Exception as exc:  # pragma: no cover
        signals["exif_error"] = str(exc)
    findings.extend(exif_findings)

    drawn: list[tuple[tuple, str]] = []  # (bbox, severity) for the overlay

    # NOISE-LOSS is the primary, reliable detector on documents: a painted/pasted/recompressed
    # region loses the page's sensor-noise floor. (Text edges are excluded from the estimate, so
    # clean documents do not fire.) ELA corroboration escalates.
    for n in noise_regions:
        corroborated = any(_overlap(n.bbox, e.bbox) for e in ela_regions)
        sev = "high" if (n.strength >= 0.5 or corroborated) else "medium"
        extra = (" Error-Level Analysis agrees on this region, so two independent signals concur."
                 if corroborated else "")
        findings.append(_finding(
            sev, "Region lost the page's noise pattern (likely edited)",
            "This region no longer carries the document's sensor/scan noise — the hallmark of "
            "content that was painted over, pasted in, or re-compressed after the original scan."
            + extra,
            {"detector": "noise", "strength": n.strength, "corroborated": corroborated},
            confidence=0.7 if corroborated else 0.6, regions=[n.bbox]))
        drawn.append((n.bbox, sev))

    # ELA regions not already covered by a noise finding.
    for r in ela_regions:
        if any(_overlap(r.bbox, n.bbox) for n in noise_regions):
            continue
        sev = _severity_for(r.strength)
        findings.append(_finding(
            sev, "Inconsistent compression (possible edit)",
            "Error-Level Analysis shows this region compresses at a different level than the rest "
            "of the document — typical of content pasted or repainted after the original was created.",
            {"detector": "ela", "strength": round(r.strength, 3)},
            confidence=0.6, regions=[r.bbox]))
        drawn.append((r.bbox, sev))

    # COPY-MOVE is corroboration-only: dense document text (repeated glyphs / amounts) makes
    # standalone clone detection unreliable, so we report a clone ONLY where it overlaps a
    # noise/ELA region. (Robust clone detection on text is the learned DocTamper model — Day 3.)
    primary = noise_regions + ela_regions
    for r in cm_regions:
        if not any(_overlap(r.bbox, p.bbox) for p in primary):
            continue
        findings.append(_finding(
            "high", "Cloned / copy-pasted region",
            "A region here duplicates another region of the page (verified by content + noise "
            "cross-correlation) and coincides with an edit signal — content cloned to cover an "
            "original value.",
            {"detector": "copy_move", "strength": r.strength}, confidence=0.8, regions=[r.bbox]))
        drawn.append((r.bbox, "high"))

    # JPEG-ghost corroborates an ELA/noise region; on its own it is only an INFO hint.
    for g in ghost_regions:
        corro = any(_overlap(g.bbox, r.bbox) for r in (ela_regions + noise_regions))
        if corro:
            findings.append(_finding(
                "medium", "Recompression ghost",
                "This region's JPEG recompression profile differs from the page, consistent with a "
                "spliced/re-saved patch (corroborates the compression/noise finding here).",
                {"detector": "jpeg_ghost"}, confidence=0.6, regions=[g.bbox]))
            drawn.append((g.bbox, "medium"))

    # ── overall verdict ──
    # Graduated (not binary): a lone HIGH finding lands in the freeze band but isn't a hard 0;
    # corroboration / multiple localized regions push it down further. CRITICAL → 0 trust.
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    sev_risk = {0: 0.0, 1: 0.15, 2: 0.45, 3: 0.85, 4: 1.0}
    top = max((rank.get(f["severity"], 0) for f in findings), default=0)
    n_region_findings = sum(1 for f in findings if f["values"].get("regions"))
    risk = min(1.0, sev_risk[top] + 0.05 * max(0, n_region_findings - 1))
    image_trust = round(100.0 * (1.0 - risk), 1)
    verdict = ("EDITED" if top >= 3 else "SUSPICIOUS" if top == 2 else "CLEAN")

    return {
        "ok": True,
        "kind": "image",
        "width": w,
        "height": h,
        "findings": findings,
        "signals": signals,
        "image_trust": image_trust,
        "verdict": verdict,
        "annotated_b64": _b64_png(_annotate(img, drawn)),
        "ela_b64": _b64_png(_ela_heatmap(ela_bm, (w, h))) if ela_bm.size else None,
    }


def _annotate(img: Image.Image, drawn: list[tuple[tuple, str]]) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    for bbox, sev in drawn:
        color = SEVERITY_COLOR.get(sev, SEVERITY_COLOR["info"])
        for i in range(3):  # thick rectangle
            d.rectangle([bbox[0] - i, bbox[1] - i, bbox[2] + i, bbox[3] + i], outline=color)
    return out


def _ela_heatmap(block_means: np.ndarray, size: tuple[int, int]) -> Image.Image:
    if block_means.size == 0:
        return Image.new("RGB", size, (0, 0, 0))
    norm = block_means / (block_means.max() + 1e-6)
    small = (norm * 255).astype(np.uint8)
    heat = Image.fromarray(small, mode="L").resize(size, Image.BILINEAR)
    # red-on-black heatmap
    rgb = Image.merge("RGB", (heat, Image.new("L", size, 0), Image.new("L", size, 0)))
    return rgb
