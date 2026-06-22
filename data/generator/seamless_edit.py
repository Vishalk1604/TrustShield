"""Seamless, field-targeted image edits with NO hard edges (plan §11).

Given a rasterised document image and the pixel box of a value, replace it with ``new_text`` at one of
three realism tiers, returning the edited image + a ground-truth mask:

    naive    — hard rectangle fill + stamped text. The easy tier: the flat fill kills the page's
               sensor noise inside a crisp rectangle, so the ELA / flat-fill / noise heuristics catch it.
    blended  — feathered alpha composite (soft edges, colours sampled from the neighbourhood). Mid.
    pro      — inpaint the original glyphs (keeps surrounding texture, no flat box), render a
               font/colour-matched value, alpha-composite it softly, then RE-ADD sensor noise matched to
               the page so there is no noise-drop, and match the scanner's optical softness. No flat
               fill, no crisp seam; the caller's single final JPEG re-encode gives the edit the page's
               compression history. This is what a careful forger actually produces — and it is meant to
               slip past the naive heuristics (that gap is the point; the learned model is what closes it).

Pure PIL/numpy with an optional OpenCV fast-path (``cv2.inpaint``); if cv2 is absent the pro tier
degrades to the blended recipe. Synthetic only; deterministic given a seeded RNG.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

Box = tuple[int, int, int, int]
DIFFICULTIES = ("naive", "blended", "pro")


# ── font / colour sampling ──────────────────────────────────────────────────────────

def _load_font(size_px: int, mono: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        names = (("consolab.ttf", "DejaVuSansMono-Bold.ttf") if bold
                 else ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"))
    else:
        names = (("arialbd.ttf", "Arialbd.ttf", "DejaVuSans-Bold.ttf", "calibrib.ttf", "LiberationSans-Bold.ttf")
                 if bold else
                 ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "calibri.ttf", "LiberationSans-Regular.ttf"))
    for n in names:
        try:
            return ImageFont.truetype(n, max(6, int(size_px)))
        except Exception:
            continue
    return ImageFont.load_default()


def _text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    try:
        return int(font.getlength(text))
    except Exception:
        return len(text) * int(getattr(font, "size", 10) * 0.6)


def _ink_color(arr: np.ndarray, box: Box) -> tuple[int, int, int]:
    """Colour of the darkest ink inside the box. Sampled dark + nudged darker so that after the soft
    glyph blur (which lightens thin strokes) the rendered value matches the page's existing ink."""
    x0, y0, x1, y1 = box
    crop = arr[y0:y1, x0:x1].reshape(-1, 3)
    if crop.size == 0:
        return (35, 35, 35)
    lum = crop.mean(axis=1)
    dark = crop[lum < np.percentile(lum, 12)]
    src = dark if len(dark) else crop
    med = np.median(src, axis=0) * 0.85
    return tuple(int(v) for v in np.clip(med, 0, 120))


def _paper_color(arr: np.ndarray, box: Box, pad: int = 6) -> tuple[int, int, int]:
    """Median colour of the bright pixels just around the box — the paper."""
    x0, y0, x1, y1 = box
    H, W = arr.shape[:2]
    crop = arr[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)].reshape(-1, 3)
    if crop.size == 0:
        return (245, 245, 245)
    lum = crop.mean(axis=1)
    bright = crop[lum > np.percentile(lum, 60)]
    src = bright if len(bright) else crop
    return tuple(int(v) for v in np.median(src, axis=0))


# ── geometry helpers ────────────────────────────────────────────────────────────────

def _box_mask(size: tuple[int, int], box: Box) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    return m


def _feathered_box(size: tuple[int, int], box: Box, feather: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather))


def _render_glyphs(size: tuple[int, int], box: Box, text: str, font: ImageFont.FreeTypeFont,
                   color: tuple[int, int, int]) -> tuple[Image.Image, Image.Image]:
    """A full-size RGB layer with `text` drawn (left-aligned, vertically centred in box) + its alpha."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGB", size, (0, 0, 0))
    alpha = Image.new("L", size, 0)
    dl, da = ImageDraw.Draw(layer), ImageDraw.Draw(alpha)
    try:
        tb = dl.textbbox((0, 0), text, font=font)
        ty = y0 + max(0, ((y1 - y0) - (tb[3] - tb[1])) // 2) - tb[1]
    except Exception:
        ty = y0 + 1
    tx = x0 + 2
    dl.text((tx, ty), text, font=font, fill=tuple(color))
    da.text((tx, ty), text, font=font, fill=255)
    return layer, alpha


# ── noise / inpaint (pro tier) ───────────────────────────────────────────────────────

def _inpaint_box(arr_rgb: np.ndarray, box: Box) -> np.ndarray:
    import cv2  # optional; pro tier degrades to blended if missing

    x0, y0, x1, y1 = box
    mask = np.zeros(arr_rgb.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = 255
    bgr = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2BGR)
    out = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def _page_noise_sigma(arr_rgb: np.ndarray, box: Box, pad: int = 10) -> float:
    """Estimate the page's sensor-noise σ from paper just outside the box (high-pass residual)."""
    x0, y0, x1, y1 = box
    H, W = arr_rgb.shape[:2]
    patch = arr_rgb[max(0, y0 - pad):min(H, y1 + pad), max(0, x0 - pad):min(W, x1 + pad)]
    if patch.size == 0:
        return 4.0
    g = patch.mean(axis=2)
    blur = np.asarray(Image.fromarray(g.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0)), dtype=np.float32)
    return float(np.clip((g - blur).std(), 1.5, 11.0))


def _add_noise(arr_rgb: np.ndarray, box: Box, sigma: float, rng: np.random.Generator) -> np.ndarray:
    x0, y0, x1, y1 = box
    out = arr_rgb.astype(np.float32)
    out[y0:y1, x0:x1] += rng.normal(0.0, sigma, out[y0:y1, x0:x1].shape)
    return np.clip(out, 0, 255).astype(np.uint8)


# ── tiers ─────────────────────────────────────────────────────────────────────────

def _naive(img: Image.Image, box: Box, text: str, font, ink, paper) -> tuple[Image.Image, Image.Image]:
    out = img.copy()
    ImageDraw.Draw(out).rectangle(box, fill=tuple(paper))     # flat fill = the tell
    layer, alpha = _render_glyphs(out.size, box, text, font, ink)
    out.paste(layer, (0, 0), alpha)
    return out, _box_mask(img.size, box)


def _blended(img: Image.Image, box: Box, text: str, font, ink, paper,
             rng: np.random.Generator) -> tuple[Image.Image, Image.Image]:
    feather = max(2, (box[3] - box[1]) // 5)
    fill = Image.new("RGB", img.size, tuple(paper))
    base = Image.composite(fill, img, _feathered_box(img.size, box, feather))
    layer, glyph_a = _render_glyphs(img.size, box, text, font, ink)
    base.paste(layer, (0, 0), glyph_a.filter(ImageFilter.GaussianBlur(0.4)))
    return base, _box_mask(img.size, box)


def _pro(img: Image.Image, box: Box, text: str, font, ink, paper,
         rng: np.random.Generator) -> tuple[Image.Image, Image.Image]:
    arr = np.asarray(img)
    try:
        base = _inpaint_box(arr, box)               # remove old glyphs, keep paper texture (no flat box)
    except Exception:
        return _blended(img, box, text, font, ink, paper, rng)
    base_img = Image.fromarray(base)
    layer, glyph_a = _render_glyphs(img.size, box, text, font, ink)
    base_img.paste(layer, (0, 0), glyph_a.filter(ImageFilter.GaussianBlur(0.35)))
    out = _add_noise(np.asarray(base_img), box, _page_noise_sigma(arr, box), rng)  # re-add page noise
    out_img = Image.fromarray(out)
    x0, y0, x1, y1 = box
    out_img.paste(out_img.crop(box).filter(ImageFilter.GaussianBlur(0.35)), (x0, y0))  # match optics
    return out_img, _box_mask(img.size, box)


_TIERS = {"naive": _naive, "blended": _blended, "pro": _pro}


def edit_field(img: Image.Image, box: Box, new_text: str, *, difficulty: str = "pro",
               font_px: Optional[int] = None, mono: bool = False, bold: bool = False,
               text_color: Optional[tuple[int, int, int]] = None,
               rng: Optional[np.random.Generator] = None) -> tuple[Image.Image, Image.Image]:
    """Replace the value in `box` with `new_text` at the given difficulty. Returns (image, mask)."""
    if difficulty not in _TIERS:
        raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
    rng = rng if rng is not None else np.random.default_rng(0)
    img = img.convert("RGB")
    arr = np.asarray(img)
    W, H = img.size
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W - 1, x1), min(H - 1, y1)
    font = _load_font(font_px or max(10, int((y1 - y0) * 0.8)), mono=mono, bold=bold)
    ink = text_color or _ink_color(arr, (x0, y0, x1, y1))
    paper = _paper_color(arr, (x0, y0, x1, y1))
    # widen the box if the replacement is longer than the original value
    x1 = min(W - 1, max(x1, x0 + _text_width(font, new_text) + 6))
    return _TIERS[difficulty](img, (x0, y0, x1, y1), new_text, font, ink, paper, rng) \
        if difficulty != "naive" else _naive(img, (x0, y0, x1, y1), new_text, font, ink, paper)
