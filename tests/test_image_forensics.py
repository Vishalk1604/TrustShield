"""Image / pixel forensics (plan §6.D1, §10 Day 1).

Builds controlled raster documents with a KNOWN tampered region and asserts the detectors
localize the edit, while a clean image produces no high-severity finding. Pure local (numpy +
Pillow); copy-move assertions are guarded on cv2 availability.
"""

import io

import numpy as np
import pytest
from PIL import Image, ImageFilter

from services.forensics.app.image_forensics import _CV2, analyze_image


def _base_doc(seed: int = 0) -> Image.Image:
    """A mid-gray, uniformly-textured 'document' with some text-like bars (a realistic JPEG base)."""
    rng = np.random.default_rng(seed)
    a = rng.integers(95, 160, size=(320, 480), dtype=np.uint8)
    for y in range(40, 300, 45):           # horizontal 'text' bars (uniform across the page)
        a[y:y + 6, 40:440] = 30
    return Image.fromarray(a, mode="L").convert("RGB")


def _save_jpeg(img: Image.Image, tmp_path, name: str, quality: int = 90) -> str:
    p = tmp_path / name
    img.save(p, "JPEG", quality=quality)
    return str(p)


def _overlaps(region_bbox, tamper_bbox) -> bool:
    a, b = region_bbox, tamper_bbox
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _region_findings(result):
    return [f for f in result["findings"] if f["values"].get("regions")]


def _max_severity(result) -> int:
    rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    return max((rank.get(f["severity"], 0) for f in result["findings"]), default=0)


def test_clean_image_has_no_high_severity(tmp_path):
    clean = _save_jpeg(_base_doc(0), tmp_path, "clean.jpg")
    res = analyze_image(clean)
    assert res["ok"] is True
    assert res["verdict"] != "EDITED"
    assert _max_severity(res) < 3, [f["title"] for f in res["findings"]]


def test_splice_is_localized_by_noise_or_ela(tmp_path):
    img = _base_doc(1)
    arr = np.array(img)
    # Splice a smooth (near-zero-noise) patch into a known box → noise/ELA anomaly there.
    tamper = (200, 120, 320, 180)  # x0,y0,x1,y1
    arr[120:180, 200:320] = 140
    tampered = _save_jpeg(Image.fromarray(arr), tmp_path, "splice.jpg")

    res = analyze_image(tampered)
    assert res["ok"] is True
    region_findings = _region_findings(res)
    assert region_findings, "expected at least one localized finding on a spliced image"
    assert any(
        _overlaps(r["bbox"], tamper)
        for f in region_findings for r in f["values"]["regions"]
    ), "no localized region overlapped the spliced area"
    assert res["verdict"] in ("EDITED", "SUSPICIOUS")
    assert res["annotated_b64"]  # an overlay image is always produced


@pytest.mark.skipif(not _CV2, reason="opencv not installed; copy-move detector unavailable")
def test_copy_move_clone_detected(tmp_path):
    img = _base_doc(2)
    arr = np.array(img)
    # Exact clone: copy an 80x80 textured block to a distant location.
    block = arr[40:120, 40:120].copy()
    arr[180:260, 320:400] = block
    clone_box = (320, 180, 400, 260)
    tampered = _save_jpeg(Image.fromarray(arr), tmp_path, "clone.jpg", quality=95)

    res = analyze_image(tampered)
    cm = [f for f in res["findings"] if f["values"].get("detector") == "copy_move"]
    assert cm, "copy-move detector did not flag an exact clone"
    assert any(_overlaps(r["bbox"], clone_box) for f in cm for r in f["values"]["regions"])
    assert res["verdict"] == "EDITED"


def test_analyze_image_handles_garbage(tmp_path):
    bad = tmp_path / "notimage.jpg"
    bad.write_bytes(b"this is not an image")
    res = analyze_image(str(bad))
    assert res["ok"] is False and res["findings"] == []
