"""Programmatic image tampering with ground-truth masks (plan §10 Day 2).

The synthetic counterpart to `tamper.py` (which forges PDF-level signals): this module forges
*pixel-level* edits into raster document images and returns, for every edit, a ground-truth mask of
exactly which pixels changed. That mask is what makes the image-forensics layer *measurable* — the
eval harness compares the detector's localized regions against it (IoU / hit-rate), and the same
tampers double as realistic demo material.

Each operation mirrors a real attacker move and the detector that should catch it:

    | function          | attacker move                                  | caught by            |
    |-------------------|------------------------------------------------|----------------------|
    | copy_move         | clone a nearby region to cover content         | copy-move (NCC)      |
    | splice            | paste foreign/smooth content                   | noise + ELA          |
    | recompress_patch  | re-save one region at a different JPEG quality | JPEG-ghost + ELA     |
    | number_edit       | white-out a value and type a new number        | ELA + noise          |

Everything is deterministic given a seeded RNG, synthetic (zero PII), and local. The builder saves
the *original* and the *tampered* image both as JPEG so the realistic "edit-then-resave" compression
history (which ELA relies on) is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

Box = tuple[int, int, int, int]  # (x0, y0, x1, y1)


@dataclass
class TamperResult:
    image: Image.Image           # tampered RGB image
    mask: Image.Image            # 'L' mask: 255 where pixels were changed
    tamper_type: str
    boxes: list[Box]             # ground-truth tampered region(s)
    meta: dict = field(default_factory=dict)


# ── helpers ───────────────────────────────────────────────────────────────────────

def _mask_with(size: tuple[int, int], boxes: list[Box]) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for b in boxes:
        d.rectangle(b, fill=255)
    return m


def _ink_density(gray: np.ndarray, block: int = 16) -> np.ndarray:
    """Fraction of 'ink' (dark) pixels per block — used to land tampers on real content."""
    h, w = gray.shape
    gh, gw = h // block, w // block
    if gh == 0 or gw == 0:
        return np.zeros((1, 1))
    ink = (gray[: gh * block, : gw * block] < 110).astype(np.float32)
    return ink.reshape(gh, block, gw, block).mean(axis=(1, 3))


def _find_content_box(img: Image.Image, rng: np.random.Generator,
                      w_frac: float = 0.22, h_frac: float = 0.06) -> Box:
    """Pick a content-dense rectangle (so the edit sits on text, not a blank margin)."""
    gray = np.asarray(img.convert("L"))
    H, W = gray.shape
    bw, bh = int(W * w_frac), int(H * h_frac)
    dens = _ink_density(gray)
    if dens.size > 1 and dens.max() > 0:
        # Score candidate top-left block positions by the ink density they would cover.
        gh, gw = dens.shape
        cand = []
        for _ in range(40):
            gy = int(rng.integers(0, max(1, gh - bh // 16)))
            gx = int(rng.integers(0, max(1, gw - bw // 16)))
            score = dens[gy:gy + max(1, bh // 16), gx:gx + max(1, bw // 16)].mean()
            cand.append((score, gx * 16, gy * 16))
        cand.sort(reverse=True)
        _, x0, y0 = cand[0]
    else:
        x0 = int(rng.integers(0, max(1, W - bw)))
        y0 = int(rng.integers(0, max(1, H - bh)))
    x0 = min(x0, W - bw)
    y0 = min(y0, H - bh)
    return (x0, y0, x0 + bw, y0 + bh)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("arial.ttf", "DejaVuSans.ttf", "Arial.ttf", "calibri.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _bg_color(img: Image.Image, box: Box) -> tuple[int, int, int]:
    """Median colour just outside the box — a plausible 'paper' fill for white-out edits."""
    x0, y0, x1, y1 = box
    pad = 6
    crop = np.asarray(img.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad)))
    flat = crop.reshape(-1, 3)
    bright = flat[flat.mean(axis=1) > 150]
    src = bright if len(bright) else flat
    return tuple(int(v) for v in np.median(src, axis=0))


# ── tamper operations ───────────────────────────────────────────────────────────────

def copy_move(img: Image.Image, rng: np.random.Generator) -> TamperResult:
    """Clone a content region onto another content region (cover-up with copied pixels)."""
    src = _find_content_box(img, rng, w_frac=0.16, h_frac=0.05)
    bw, bh = src[2] - src[0], src[3] - src[1]
    W, H = img.size
    # destination: shifted well away from the source
    dx = int(rng.choice([-1, 1])) * int(W * rng.uniform(0.2, 0.35))
    dy = int(rng.choice([-1, 1])) * int(H * rng.uniform(0.08, 0.18))
    dst_x = int(np.clip(src[0] + dx, 0, W - bw))
    dst_y = int(np.clip(src[1] + dy, 0, H - bh))
    dst: Box = (dst_x, dst_y, dst_x + bw, dst_y + bh)
    out = img.copy()
    out.paste(img.crop(src), (dst_x, dst_y))
    return TamperResult(out, _mask_with(img.size, [dst]), "copy_move", [dst],
                        {"src": src, "dst": dst})


def splice(img: Image.Image, rng: np.random.Generator) -> TamperResult:
    """Paste a foreign, lightly-blurred patch (different noise + compression) over content."""
    box = _find_content_box(img, rng, w_frac=0.2, h_frac=0.06)
    W, H = img.size
    # take a patch from a distant area, blur it (kills its native noise), paste it in
    src = _find_content_box(img, np.random.default_rng(int(rng.integers(1 << 30))),
                            w_frac=0.2, h_frac=0.06)
    patch = img.crop(src).resize((box[2] - box[0], box[3] - box[1])).filter(
        ImageFilter.GaussianBlur(1.2))
    out = img.copy()
    out.paste(patch, (box[0], box[1]))
    return TamperResult(out, _mask_with(img.size, [box]), "splice", [box], {"src": src, "dst": box})


def recompress_patch(img: Image.Image, rng: np.random.Generator, quality: int = 45) -> TamperResult:
    """Re-save one region at a very different JPEG quality and paste it back (JPEG-ghost)."""
    import io

    box = _find_content_box(img, rng, w_frac=0.22, h_frac=0.07)
    region = img.crop(box)
    buf = io.BytesIO()
    region.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    out = img.copy()
    out.paste(Image.open(buf).convert("RGB"), (box[0], box[1]))
    return TamperResult(out, _mask_with(img.size, [box]), "recompress", [box], {"quality": quality})


def number_edit(img: Image.Image, rng: np.random.Generator,
                new_value: Optional[str] = None) -> TamperResult:
    """White-out a value and type a new number over it — the 'edited a digit' attack."""
    box = _find_content_box(img, rng, w_frac=0.2, h_frac=0.05)
    x0, y0, x1, y1 = box
    out = img.copy()
    d = ImageDraw.Draw(out)
    d.rectangle(box, fill=_bg_color(img, box))
    if new_value is None:
        new_value = format(int(rng.integers(100000, 9999999)), ",")
    font = _load_font(max(12, int((y1 - y0) * 0.8)))
    d.text((x0 + 3, y0 + 1), new_value, fill=(20, 20, 20), font=font)
    return TamperResult(out, _mask_with(img.size, [box]), "number_edit", [box],
                        {"new_value": new_value})


# Registry of tamper types (deterministic order for reproducible datasets).
TAMPERS = {
    "copy_move": copy_move,
    "splice": splice,
    "recompress": recompress_patch,
    "number_edit": number_edit,
}
