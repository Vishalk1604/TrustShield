"""Tests for the ingestion loader + extractors + orchestrator (plan.md §7, Week 1).

Runs on the committed synthetic packets + text fixtures + an on-the-fly encrypted PDF.
OCR is not required for these (synthetic PDFs carry a text layer).
"""

import json
from pathlib import Path

import fitz
import pytest

from services.forensics.app.ingest.loader import load_text
from services.forensics.app.ingest.pipeline import ingest_document
from services.forensics.app.ingest.extract.pan import extract_pan
from services.forensics.app.ingest.extract.aadhaar import extract_aadhaar

ROOT = Path(__file__).resolve().parents[1]
PACKETS_DIR = ROOT / "data" / "synthetic" / "packets"


def _find_doc(doc_type: str):
    """First (path) of a document of `doc_type` across the synthetic packets."""
    if not PACKETS_DIR.exists():
        return None
    for pkt in sorted(PACKETS_DIR.iterdir()):
        mp = pkt / "manifest.json"
        if not mp.exists():
            continue
        for d in json.loads(mp.read_text()).get("documents", []):
            if d.get("doc_type") == doc_type:
                return pkt / d["filename"]
    return None


# --------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------

def test_loader_reads_embedded_text():
    path = _find_doc("form16")
    if path is None:
        pytest.skip("no synthetic form16 found")
    ld = load_text(str(path))
    assert ld.ok and ld.source == "embedded" and not ld.ocr_used
    assert "FORM NO. 16" in ld.text.upper()   # realistic TRACES title ("FORM NO. 16 [See rule 31(1)(a)]")


def test_loader_password_protected(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "FORM NO. 16\nGross Salary Rs. 12,00,000\nTDS")
    path = str(tmp_path / "enc.pdf")
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="open123", owner_pw="own123")
    doc.close()

    blocked = load_text(path)
    assert blocked.needs_password and not blocked.ok
    opened = load_text(path, password="open123")
    assert opened.ok and "FORM" in opened.text.upper()


# --------------------------------------------------------------------------
# KYC extractors (real-OCR-style text fixtures)
# --------------------------------------------------------------------------

def test_extract_pan_freeform_ocr():
    text = "INCOME TAX DEPARTMENT\nGOVT. OF INDIA\nABCPV1234D\nName: RAHUL SHARMA\nDate of Birth: 12/03/1990"
    r = extract_pan(text)
    assert r["pan"] == "ABCPV1234D"
    assert r["name"].startswith("RAHUL")
    assert r["dob"] == "1990-03-12"


def test_extract_aadhaar_masked():
    text = "Government of India\nName: Priya Verma\nDOB: 05/08/1992\nFEMALE\nXXXX XXXX 1234\nUIDAI"
    r = extract_aadhaar(text)
    assert r["aadhaar"] == "XXXXXXXX1234"
    assert r["gender"] == "FEMALE"
    assert r["dob"] == "1992-08-05"


# --------------------------------------------------------------------------
# End-to-end orchestrator on synthetic docs
# --------------------------------------------------------------------------

def test_ingest_identity_classifies_pan_and_validates():
    path = _find_doc("identity")
    if path is None:
        pytest.skip("no synthetic identity/PAN doc found")
    out = ingest_document(str(path))   # doc_type inferred
    assert out["ok"] and out["doc_type"] == "pan"
    assert out["schema_doc_type"] == "identity"
    assert out["fields"].get("pan")
    assert out["kyc"]["pan"]["valid"] is True   # synthetic PANs are structurally valid


def test_ingest_form16_extracts_income():
    path = _find_doc("form16")
    if path is None:
        pytest.skip("no synthetic form16 found")
    out = ingest_document(str(path))
    assert out["ok"] and out["doc_type"] == "form16"
    assert out["fields"].get("gross_income") is not None
