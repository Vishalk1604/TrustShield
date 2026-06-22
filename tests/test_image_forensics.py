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
    """An ID-card-sized 'paper' page with text bars + a realistic sensor-noise floor (σ≈12).
    Card-sized (800x1080) so a number-sized edit (~180x55 px) is a small fraction of the page —
    the noise detector's size cap (drops >2% glare/background blobs) targets exactly that regime."""
    rng = np.random.default_rng(seed)
    a = np.full((1080, 800), 226, dtype=np.float32)
    for y in range(60, 1000, 64):                # uniform text-like bars
        a[y:y + 10, 60:720] = 40
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


def _digital_doc() -> Image.Image:
    """A pristine, noise-free digital render (e.g. an e-PAN / PDF screenshot) — the case where the
    noise/ELA detectors can't fire and only the flat-fill detector can. Uses VARIED text (not a
    repeated glyph lattice) so it doesn't look like a periodic screen grid to the recapture detector."""
    a = np.full((360, 520), 250, dtype=np.uint8)         # clean white 'paper', no sensor noise
    img = Image.fromarray(a, mode="L").convert("RGB")
    d = ImageDraw.Draw(img)
    rows = ["PAN: ABCDE1234F", "Name: Rahul Sharma", "Date of Birth: 16/08/1990",
            "Father's Name: Vikas Kumar", "Address: 12 MG Road, Bengaluru 560001",
            "Issued on: 02/07/2024", "Acknowledgement: 9087-6543-2100"]
    for i, t in enumerate(rows):                          # crisp 'printed' text, varied per row
        d.text((50, 40 + i * 40), t, fill=(15, 15, 15))
    return img


def test_clean_digital_doc_not_flagged(tmp_path):
    p = tmp_path / "digital_clean.png"
    _digital_doc().save(p)
    res = analyze_image(str(p))
    assert res["verdict"] == "CLEAN" and len(res["findings"]) == 0


def test_digital_paint_over_is_flagged(tmp_path):
    """A flat colour painted over a value on a pristine digital doc (Sketchbook-style) is caught by
    the flat-fill detector even with no sensor-noise / JPEG trace."""
    img = _digital_doc()
    box = (150, 120, 360, 156)
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=(232, 232, 228))                # paint over, then retype a new value
    d.text((156, 124), "ABCDE1234F", fill=(20, 20, 20))
    p = tmp_path / "digital_paint.png"
    img.save(p)

    res = analyze_image(str(p))
    assert res["verdict"] in ("EDITED", "SUSPICIOUS")
    fills = [f for f in res["findings"] if f["values"].get("detector") == "flat_fill"]
    assert fills, "flat-fill detector did not flag the paint-over"
    assert any(_overlaps(r["bbox"], box) for f in fills for r in f["values"]["regions"])


def test_analyze_image_handles_garbage(tmp_path):
    bad = tmp_path / "notimage.jpg"
    bad.write_bytes(b"this is not an image")
    res = analyze_image(str(bad))
    assert res["ok"] is False and res["findings"] == []


def test_compute_verdict_levels():
    from services.forensics.app.image_forensics import compute_verdict
    assert compute_verdict([])[0] == "CLEAN"
    v, t = compute_verdict([{"severity": "high", "values": {}}])
    assert v == "EDITED" and t < 30
    assert compute_verdict([{"severity": "medium", "values": {}}])[0] == "SUSPICIOUS"


def test_tampered_pan_number_is_captured_and_flagged():
    """A PAN whose trailing letter was painted out is captured and flagged invalid — the semantic
    catch behind /forensics/analyze-image's identifier check (works when pixels can't see the edit)."""
    from services.forensics.app.ingest.extract.pan import extract_pan
    from services.forensics.app.ingest.normalize import validate_pan
    edited = extract_pan("Permanent Account Number Card\nPATPK4316\nName VISHAL KARUN")
    assert edited["pan"] == "PATPK4316"                       # malformed PAN is captured…
    assert validate_pan(edited["pan"])["valid"] is False      # …and flagged invalid
    genuine = extract_pan("PATPK4316K")
    assert genuine["pan"] == "PATPK4316K" and validate_pan(genuine["pan"])["valid"] is True
