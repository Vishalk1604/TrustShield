"""Build a labeled clean/tampered IMAGE dataset for the image-forensics eval (plan §10 Day 2).

Rasterises the committed synthetic loan PDFs to images (so the documents look real — bank
statements, Form 16, PAN, salary slips), saves each as a JPEG "scan", then forges a set of
pixel-level edits (`tamper_image.py`) with ground-truth masks. The result is what the eval harness
measures the detectors against and what the demo shows.

Deterministic (fixed seed) and synthetic (zero PII). Output goes under
`data/synthetic/images/` which is gitignored — it is regenerated on demand:

    python -m data.generator.build_image_dataset            # default ~12 sources × (1 clean + 4 tampers)

Layout written:
    data/synthetic/images/
      clean/<src>.jpg
      tampered/<src>__<tamper>.jpg
      masks/<src>__<tamper>.png        (255 = tampered pixels)
      labels.json                      (every record: file, label, tamper_type, mask, boxes, source)
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from data.generator.tamper_image import TAMPERS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKETS = REPO_ROOT / "data" / "synthetic" / "packets"
DEFAULT_OUT = REPO_ROOT / "data" / "synthetic" / "images"

# Prefer text-dense financial/KYC docs (good tamper targets); deterministic preference order.
PREFERRED_DOCS = ("form16.pdf", "bank_statement.pdf", "salary_slip.pdf", "identity.pdf")


def _rasterize(pdf_path: Path, dpi: int) -> Image.Image:
    """Render page 1 of a PDF to a PIL RGB image."""
    with fitz.open(pdf_path) as doc:
        pix = doc[0].get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def _simulate_scan(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Give a vector-clean render the characteristics of a real scan/photo: a faint lighting
    gradient, mild optical blur, and a consistent sensor-noise floor. This baseline is what makes
    edits detectable — a painted/pasted region won't carry the page's noise/blur, so the
    forensics can localize it (without it, a synthetic 'edit' is forensically invisible)."""
    from PIL import ImageFilter

    a = np.asarray(img, dtype=np.float32)
    h, w, _ = a.shape
    # faint diagonal lighting gradient (0.90–1.0)
    gy = np.linspace(rng.uniform(0.90, 0.96), 1.0, h)[:, None]
    gx = np.linspace(rng.uniform(0.95, 1.0), 1.0, w)[None, :]
    a *= (gy * gx)[:, :, None]
    img2 = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    img2 = img2.filter(ImageFilter.GaussianBlur(0.6))           # scanner optical softness
    a = np.asarray(img2, dtype=np.float32)
    # A real scan/photo carries a sensor-noise floor that survives JPEG. We add σ≈12 pre-JPEG so
    # the post-compression floor (~4–5) is detectable — an edited region that lacks it stands out.
    a += rng.normal(0.0, 12.0, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _iter_sources(packets_dir: Path, limit: int) -> list[tuple[str, Path]]:
    """Pick a deterministic, varied set of (source_id, pdf_path) across packets + doc types."""
    sources: list[tuple[str, Path]] = []
    for pkt in sorted(packets_dir.iterdir()):
        if not pkt.is_dir():
            continue
        for name in PREFERRED_DOCS:
            p = pkt / name
            if p.exists():
                sid = f"{pkt.name}_{name.replace('.pdf', '')}"
                sources.append((sid, p))
                break  # one doc per packet → maximises layout/content variety
        if len(sources) >= limit:
            break
    return sources


def build_dataset(out_dir: Path = DEFAULT_OUT, packets_dir: Path = DEFAULT_PACKETS,
                  n_sources: int = 12, dpi: int = 150, jpeg_quality: int = 90,
                  seed: int = 7) -> dict:
    """Generate the dataset and return a summary dict. Idempotent (clears the output dir)."""
    out_dir = Path(out_dir)
    for sub in ("clean", "tampered", "masks"):
        d = out_dir / sub
        if d.exists():
            for f in d.glob("*"):
                f.unlink()
        d.mkdir(parents=True, exist_ok=True)

    sources = _iter_sources(Path(packets_dir), n_sources)
    if not sources:
        raise SystemExit(f"no source PDFs under {packets_dir} — run the packet generator first")

    records: list[dict] = []
    for idx, (sid, pdf) in enumerate(sources):
        scan_rng = np.random.default_rng(seed * 31 + idx)
        base = _simulate_scan(_rasterize(pdf, dpi), scan_rng)
        # Persist the clean "scan" as JPEG, then RE-LOAD it so tampers act on the compressed
        # image (realistic edit-then-resave history that ELA depends on).
        clean_path = out_dir / "clean" / f"{sid}.jpg"
        base.save(clean_path, "JPEG", quality=jpeg_quality)
        scan = Image.open(clean_path).convert("RGB")
        records.append({"id": sid, "file": f"clean/{sid}.jpg", "label": "clean",
                        "tamper_type": None, "source": pdf.name})

        for t_idx, (tname, fn) in enumerate(TAMPERS.items()):
            rng = np.random.default_rng(seed + idx * 100 + t_idx)
            res = fn(scan.copy(), rng)
            t_path = out_dir / "tampered" / f"{sid}__{tname}.jpg"
            m_path = out_dir / "masks" / f"{sid}__{tname}.png"
            res.image.save(t_path, "JPEG", quality=jpeg_quality)
            res.mask.save(m_path, "PNG")
            records.append({
                "id": f"{sid}__{tname}", "file": f"tampered/{sid}__{tname}.jpg",
                "label": "tampered", "tamper_type": tname,
                "mask": f"masks/{sid}__{tname}.png",
                "boxes": [list(map(int, b)) for b in res.boxes], "source": pdf.name,
            })

    summary = {
        "n_sources": len(sources), "dpi": dpi, "jpeg_quality": jpeg_quality, "seed": seed,
        "tamper_types": list(TAMPERS.keys()),
        "n_clean": sum(1 for r in records if r["label"] == "clean"),
        "n_tampered": sum(1 for r in records if r["label"] == "tampered"),
        "records": records,
    }
    (out_dir / "labels.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    s = build_dataset()
    print(f"Built image dataset: {s['n_clean']} clean + {s['n_tampered']} tampered "
          f"({len(s['tamper_types'])} tamper types) -> {DEFAULT_OUT}")


if __name__ == "__main__":
    main()
