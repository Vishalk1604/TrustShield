"""Throwaway Phase-C gate (plan §11): render ONE clean Form 16 + ONE seamless `pro` edit (and a
`naive` edit for contrast), then report what the heuristic detector sees. Not a test — a visual/qa gate.

    python -m data.generator._preview_form16

Writes PNG/JPEG previews under data/synthetic/_preview/ and prints, for clean / naive / pro:
the heuristic verdict (expect: clean→CLEAN, naive→flagged, pro→CLEAN i.e. seamless).
"""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from data.generator import pdf_builder as pb
from data.generator import seamless_edit as se
from data.generator.build_image_dataset import _simulate_scan

DPI = 150
SCALE = DPI / 72.0
OUT = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "_preview"


def _verdict(path: Path) -> str:
    from services.forensics.app.image_forensics import analyze_image
    res = analyze_image(str(path))
    findings = res.get("findings", res.get("signals", []))
    return f"{res.get('verdict', '?')}  (findings={len(findings) if hasattr(findings, '__len__') else '?'})"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fields: dict = {}
    meta = pb.DocMeta(creation_date=None, mod_date=None)
    doc = pb.build_form16("Rahul Sharma", "ABMPS1234F", "Infosys Limited",
                          1820000, 327600, "2023-24", meta, fields=fields, template=0)

    # render the vector PDF (for eyeballing the layout) + rasterize→scan→clean JPEG
    doc.save(str(OUT / "form16_clean.pdf"))
    page = doc[0]
    page.get_pixmap(dpi=DPI).save(str(OUT / "form16_layout.png"))  # crisp, for layout review
    base = _simulate_scan(
        Image.open(io.BytesIO(page.get_pixmap(dpi=DPI).tobytes("png"))).convert("RGB"),
        np.random.default_rng(7))
    clean_path = OUT / "form16_clean.jpg"
    base.save(clean_path, "JPEG", quality=90)
    scan = Image.open(clean_path).convert("RGB")
    doc.close()

    print("field map:", {k: (v["value"], v["fraud"]) for k, v in fields.items()})
    f = fields["gross_salary"]
    box = tuple(v * SCALE for v in f["rect_pts"])
    new_text = pb._money(round(f["amount"] * 1.5))               # inflate gross ×1.5
    font_px = round(f["size"] * SCALE)
    print(f"editing gross_salary {f['value']} -> {new_text}  box_px={tuple(round(v) for v in box)}")

    for diff in ("naive", "pro"):
        img, mask = se.edit_field(scan.copy(), box, new_text, difficulty=diff,
                                  font_px=font_px, rng=np.random.default_rng(11))
        img.save(OUT / f"form16_{diff}.jpg", "JPEG", quality=90)
        mask.save(OUT / f"form16_{diff}_mask.png")

    print("\nheuristic detector verdicts:")
    for tag, p in (("clean", clean_path), ("naive", OUT / "form16_naive.jpg"), ("pro", OUT / "form16_pro.jpg")):
        try:
            print(f"  {tag:6s} -> {_verdict(p)}")
        except Exception as e:  # forensics deps may be missing in a bare env
            print(f"  {tag:6s} -> (analyze_image unavailable: {e})")
    print(f"\npreviews in {OUT}")


if __name__ == "__main__":
    main()
