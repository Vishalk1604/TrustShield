"""Tests for POST /forensics/ingest (plan.md §7, Week 1) — the real-document upload path.

Uploads committed synthetic PDFs through the HTTP endpoint (in-process TestClient, no
sockets) and checks doc-type inference, field extraction, KYC validation, and the
forensic block.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.forensics.app.main import app

ROOT = Path(__file__).resolve().parents[1]
PACKETS_DIR = ROOT / "data" / "synthetic" / "packets"

client = TestClient(app)


def _find_doc(doc_type: str):
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


def test_ingest_endpoint_classifies_extracts_validates():
    pan_path = _find_doc("identity")
    f16_path = _find_doc("form16")
    if not (pan_path and f16_path):
        pytest.skip("synthetic identity/form16 not found")

    files = [
        ("files", ("pan_card.pdf", pan_path.read_bytes(), "application/pdf")),
        ("files", ("form16.pdf", f16_path.read_bytes(), "application/pdf")),
    ]
    resp = client.post("/forensics/ingest", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2

    by_type = {d["doc_type"]: d for d in body["documents"]}
    assert "pan" in by_type, by_type
    pan = by_type["pan"]
    assert pan["ok"] and pan["schema_doc_type"] == "identity"
    assert pan["fields"].get("pan") and pan["kyc"]["pan"]["valid"] is True
    assert "forensic" in pan and "findings" in pan["forensic"]

    assert "form16" in by_type
    assert by_type["form16"]["fields"].get("gross_income") is not None


def test_ingest_requires_a_file():
    resp = client.post("/forensics/ingest")
    assert resp.status_code == 422  # missing required 'files'
