"""Tests for the re-OCR cross-check (§6.D2) and tamper localization (§6.D3).

The re-OCR check renders each page, OCRs it, and flags currency amounts / PANs that
are present in the PDF text layer but not visible on the rendered page (the classic
whiteout: original survives in the content stream, forged value shown on top).

OCR-dependent assertions skip cleanly where Tesseract is unavailable (so CI without it
still passes); the structural pieces (whitebox regions, overlay rendering) always run.
"""

import json
from pathlib import Path

import pytest

from services.forensics.app.analyzer import (
    analyze_pdf,
    render_tamper_overlay,
    _edit_distance_le1,
    _is_visible,
)
from services.forensics.app.ocr import tesseract_available

ROOT = Path(__file__).resolve().parents[1]
PACKETS_DIR = ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = ROOT / "data" / "synthetic" / "labels.json"

needs_tesseract = pytest.mark.skipif(
    not tesseract_available(), reason="Tesseract not installed — re-OCR check no-ops"
)


@pytest.fixture(scope="module")
def labels() -> dict:
    if not LABELS_PATH.exists():
        pytest.skip("Synthetic packets not generated — run python -m data.generator.generate")
    return json.loads(LABELS_PATH.read_text())


def _reocr_findings(pkt_id: str) -> list[dict]:
    """All re-OCR findings (check=reocr) across a packet's documents."""
    pkt_dir = PACKETS_DIR / pkt_id
    manifest = json.loads((pkt_dir / "manifest.json").read_text())
    out: list[dict] = []
    for doc in manifest["documents"]:
        result = analyze_pdf(
            str(pkt_dir / doc["filename"]),
            doc_type=doc.get("doc_type", "other"),
            filename=doc["filename"],
        )
        out.extend(
            f for f in result["findings"] if (f.get("values") or {}).get("check") == "reocr"
        )
    return out


# --------------------------------------------------------------------------
# D2 — re-OCR cross-check
# --------------------------------------------------------------------------

@needs_tesseract
def test_reocr_fires_on_edited_income(labels: dict) -> None:
    """A whiteboxed (inflated) income figure leaves the original in the text layer."""
    edited = [p for p, v in labels.items() if "edited_income_figure" in (v.get("fraud_types") or [])]
    assert edited, "No edited_income_figure packet in labels.json"
    for pkt_id in edited:
        findings = _reocr_findings(pkt_id)
        assert findings, f"{pkt_id}: expected a re-OCR finding for the hidden income"
        f = findings[0]["values"]
        assert f["hidden_text_layer_value"]            # the concealed original
        assert f["regions"] and f["regions"][0]["page"] == 1


@needs_tesseract
def test_reocr_fires_on_tampered_encumbrance(labels: dict) -> None:
    """The tampered EC shows NIL but hides a registered charge in the text layer."""
    ec = [p for p, v in labels.items() if "tampered_encumbrance" in (v.get("fraud_types") or [])]
    assert ec, "No tampered_encumbrance packet in labels.json"
    findings = _reocr_findings(ec[0])
    assert findings, "Expected a re-OCR finding for the concealed charge amount"
    # The EC visually claims NIL, so nothing is "visible" — the charge is purely hidden.
    assert findings[0]["values"]["hidden_text_layer_value"]
    assert findings[0]["values"]["visible_values"] == []


@needs_tesseract
def test_reocr_zero_false_positives_on_clean_packets(labels: dict) -> None:
    """The critical guard: clean packets must produce no re-OCR findings."""
    clean = [p for p, v in labels.items() if v.get("label") == "clean"]
    assert clean, "No clean packets in labels.json"
    offenders = {p: _reocr_findings(p) for p in clean}
    offenders = {p: f for p, f in offenders.items() if f}
    assert not offenders, f"Re-OCR false positives on clean packets: {list(offenders)}"


@needs_tesseract
def test_reocr_findings_are_tagged_for_model_exclusion(labels: dict) -> None:
    """Every re-OCR finding carries values.check == 'reocr' (so features.py can drop it)."""
    edited = next(p for p, v in labels.items() if "edited_income_figure" in (v.get("fraud_types") or []))
    for f in _reocr_findings(edited):
        assert f["values"]["check"] == "reocr"
        assert f["category"] == "forensic"
        assert f["severity"] == "high"


# --------------------------------------------------------------------------
# D3 — tamper localization (structural; no Tesseract needed)
# --------------------------------------------------------------------------

def test_whitebox_finding_carries_regions(labels: dict) -> None:
    """White-box findings localise the edit with a page + bbox (drives the UI overlay)."""
    pkt_id = next(
        p for p, v in labels.items()
        if "edited_income_figure" in (v.get("fraud_types") or [])
    )
    pkt_dir = PACKETS_DIR / pkt_id
    manifest = json.loads((pkt_dir / "manifest.json").read_text())
    found_regions = False
    for doc in manifest["documents"]:
        result = analyze_pdf(str(pkt_dir / doc["filename"]),
                             doc_type=doc.get("doc_type", "other"), filename=doc["filename"])
        for f in result["findings"]:
            if "White-box" in f["title"]:
                regions = f["values"].get("regions")
                assert regions, "white-box finding must carry regions"
                bbox = regions[0]["bbox"]
                assert regions[0]["page"] >= 1
                assert len(bbox) == 4 and bbox[2] > bbox[0] and bbox[3] > bbox[1]
                found_regions = True
    assert found_regions, "No white-box finding found to localise"


def test_render_tamper_overlay_returns_png(labels: dict) -> None:
    """The overlay renderer produces a PNG for a real region (PyMuPDF only — no OCR)."""
    pkt_dir = PACKETS_DIR / next(
        p for p, v in labels.items() if "edited_income_figure" in (v.get("fraud_types") or [])
    )
    region = [{"page": 1, "bbox": [318.0, 233.0, 425.0, 254.0]}]
    # find the doc that has a whitebox region
    manifest = json.loads((pkt_dir / "manifest.json").read_text())
    doc = next(d for d in manifest["documents"] if d["doc_type"] == "form16")
    png = render_tamper_overlay(str(pkt_dir / doc["filename"]), region)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 1000


def test_render_tamper_overlay_graceful_on_bad_input() -> None:
    assert render_tamper_overlay("does-not-exist.pdf", [{"page": 1, "bbox": [0, 0, 1, 1]}]) == b""
    assert render_tamper_overlay("anything.pdf", []) == b""


# --------------------------------------------------------------------------
# Matching primitives (the precision logic)
# --------------------------------------------------------------------------

def test_edit_distance_le1() -> None:
    assert _edit_distance_le1("145000", "145000")       # identical
    assert _edit_distance_le1("145000", "146000")       # one substitution
    assert _edit_distance_le1("143500", "43500")        # one deletion (OCR dropped leading 1)
    assert not _edit_distance_le1("1450000", "2755000")  # genuinely different value


def test_is_visible_distinguishes_misread_from_hidden() -> None:
    # OCR misread: 143,500 rendered, read as 43,500 (43,500 is not its own value) -> visible
    assert _is_visible("143500", {"43500"}, {"143500"})
    # Genuine hide: 1,450,000 covered; nearest token 145,000 is the real TDS -> still hidden
    assert not _is_visible("1450000", {"145000", "2755000"}, {"1450000", "145000", "2755000"})
    # Absent entirely (EC NIL case) -> hidden
    assert not _is_visible("4200000", {"2024", "560038"}, {"4200000"})
