"""Tests for the web-app backend (plan §A): auth (register/login/role guard) + the case
submission → score → review flow. In-process TestClient; SQLite + case store in a tmp dir.
"""

import json
import os
import tempfile
from pathlib import Path

# Redirect all persistence to a throwaway dir BEFORE importing the app.
_TMP = tempfile.mkdtemp(prefix="ts_webapp_")
os.environ["TRUSTSHIELD_DB"] = str(Path(_TMP) / "test.db")
os.environ["TRUSTSHIELD_CASE_STORE"] = str(Path(_TMP) / "cases")
os.environ["TRUSTSHIELD_GRAPH_STORE"] = str(Path(_TMP) / "g.pkl")

import pytest
from fastapi.testclient import TestClient

from services.risk.app import db
from services.risk.app.main import app

ROOT = Path(__file__).resolve().parents[1]
PACKETS_DIR = ROOT / "data" / "synthetic" / "packets"

db.init_db()
client = TestClient(app)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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


def test_register_login_and_guards():
    r = client.post("/auth/register",
                    json={"email": "admin@demo.com", "password": "secret1", "role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"

    r = client.post("/auth/register", json={"email": "user@demo.com", "password": "secret1"})
    assert r.status_code == 200 and r.json()["role"] == "user"

    # duplicate email rejected; weak password rejected; bad email rejected
    assert client.post("/auth/register",
                       json={"email": "user@demo.com", "password": "secret1"}).status_code == 409
    assert client.post("/auth/register",
                       json={"email": "x@y.com", "password": "12"}).status_code == 400
    assert client.post("/auth/register",
                       json={"email": "notanemail", "password": "secret1"}).status_code == 400

    # login good/bad
    assert client.post("/auth/login",
                       json={"email": "user@demo.com", "password": "secret1"}).status_code == 200
    assert client.post("/auth/login",
                       json={"email": "user@demo.com", "password": "nope"}).status_code == 401

    # /cases requires a token
    assert client.get("/cases").status_code == 401


def test_submit_score_and_review_flow():
    user = client.post("/auth/login",
                       json={"email": "user@demo.com", "password": "secret1"}).json()
    admin = client.post("/auth/login",
                        json={"email": "admin@demo.com", "password": "secret1"}).json()

    f16, pan = _find_doc("form16"), _find_doc("identity")
    if not (f16 and pan):
        pytest.skip("synthetic form16/identity not found")

    files = [
        ("files", ("form16.pdf", f16.read_bytes(), "application/pdf")),
        ("files", ("pan.pdf", pan.read_bytes(), "application/pdf")),
    ]
    r = client.post("/cases", data={"purpose": "loan"}, files=files, headers=_hdr(user["token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["trust_score"] is not None and body["action"] in (
        "approve", "manual_review", "freeze")
    case_id = body["case_id"]
    # PAN doc was classified + KYC-validated
    pan_doc = next((d for d in body["documents"] if d["doc_type"] == "pan"), None)
    assert pan_doc and pan_doc["kyc"]["pan"]["valid"] is True

    # user sees own case; admin sees it too
    mine = client.get("/cases", headers=_hdr(user["token"])).json()
    assert any(c["id"] == case_id for c in mine["cases"])
    all_cases = client.get("/cases", headers=_hdr(admin["token"])).json()
    assert all_cases["role"] == "admin" and any(c["id"] == case_id for c in all_cases["cases"])

    # admin opens full detail
    det = client.get(f"/cases/{case_id}", headers=_hdr(admin["token"]))
    assert det.status_code == 200
    dj = det.json()
    assert dj["decision"]["trust_score"]["overall"] is not None
    assert len(dj["documents"]) >= 1


def test_user_cannot_see_others_cases():
    # a second user must not access the first user's case
    client.post("/auth/register", json={"email": "user2@demo.com", "password": "secret1"})
    u2 = client.post("/auth/login",
                     json={"email": "user2@demo.com", "password": "secret1"}).json()
    u1 = client.post("/auth/login",
                     json={"email": "user@demo.com", "password": "secret1"}).json()
    u1_cases = client.get("/cases", headers=_hdr(u1["token"])).json()["cases"]
    if not u1_cases:
        pytest.skip("no case to check ownership against")
    cid = u1_cases[0]["id"]
    assert client.get(f"/cases/{cid}", headers=_hdr(u2["token"])).status_code == 403
