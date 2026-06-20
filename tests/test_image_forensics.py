"""Image / pixel forensics (plan §6.D1, §10 Day 1–2).

Builds noisy 'scanned' documents (a sensor-noise floor, like a real scan/photo) with a KNOWN
edited region and asserts the detector localizes the edit while a clean scan stays clean. The
noise-loss detector is the reliable primary; copy-move is corroboration-only (validated in the
eval harness), so these tests exercise the paint/splice path that the demo depends on.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from services.forensics.app.image_forensics import analyze_image


def _noisy_doc(seed: int = 0) -> Image.Image:
    """A light 'paper' page with text bars + a realistic sensor-noise floor (σ≈12)."""
    rng = np.random.default_rng(seed)
    a = np.full((360, 520), 226, dtype=np.float32)
    for y in range(40, 330, 42):                 # uniform text-like bars
        a[y:y + 7, 40:470] = 40
    a += rng.normal(0.0, 12.0, a.shape)          # sensor noise (survives JPEG → a detectable floor)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGB")


def _save_reload(img: Image.Image, tmp_path, name: str, q: int = 90):
    p = tmp_path / name
    img.save(p, "JPEG", quality=q)
    return Image.open(p).convert("RGB"), str(p)


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _region_findings(res):
    return [f for f in res["findings"] if f["values"].get("regions")]


def _max_sev(res) -> int:
    rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    return max((rank.get(f["severity"], 0) for f in res["findings"]), default=0)


def test_clean_scan_has_no_high_severity(tmp_path):
    _, path = _save_reload(_noisy_doc(0), tmp_path, "clean.jpg")
    res = analyze_image(path)
    assert res["ok"] is True
    assert res["verdict"] != "EDITED", [f["title"] for f in res["findings"]]
    assert _max_sev(res) < 3


def test_painted_number_is_localized(tmp_path):
    scan, _ = _save_reload(_noisy_doc(1), tmp_path, "base.jpg")
    box = (150, 120, 330, 175)                   # white-out + retype a value (no sensor noise here)
    d = ImageDraw.Draw(scan)
    d.rectangle(box, fill=(226, 226, 226))
    d.text((156, 126), "1,234,567", fill=(20, 20, 20))
    scan.save(tmp_path / "paint.jpg", "JPEG", quality=90)

    res = analyze_image(str(tmp_path / "paint.jpg"))
    assert res["verdict"] in ("EDITED", "SUSPICIOUS")
    rf = _region_findings(res)
    assert rf, "expected a localized finding on a painted region"
    assert any(_overlaps(r["bbox"], box) for f in rf for r in f["values"]["regions"])
    assert res["annotated_b64"]


def test_spliced_patch_is_localized(tmp_path):
    scan, _ = _save_reload(_noisy_doc(2), tmp_path, "base2.jpg")
    box = (60, 220, 300, 285)
    patch = scan.crop((60, 40, 300, 105)).filter(ImageFilter.GaussianBlur(1.2))  # foreign, low-noise
    scan.paste(patch, (box[0], box[1]))
    scan.save(tmp_path / "splice.jpg", "JPEG", quality=90)

    res = analyze_image(str(tmp_path / "splice.jpg"))
    rf = _region_findings(res)
    assert rf and any(_overlaps(r["bbox"], box) for f in rf for r in f["values"]["regions"])


def test_analyze_image_handles_garbage(tmp_path):
    bad = tmp_path / "notimage.jpg"
    bad.write_bytes(b"this is not an image")
    res = analyze_image(str(bad))
    assert res["ok"] is False and res["findings"] == []
