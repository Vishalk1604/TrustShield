"""Case submission + review (plan §A): a user uploads documents for a purpose (KYC / loan /
other); the system ingests, scores, and persists the case; the admin reviews everything.

Reuses the built ingestion (`ingest_document`) + the full scoring pipeline
(`aggregator.score_packet_dir`). Real-upload scoring leans on the deterministic forensic +
semantic + KYC signals; the synthetic-only behavioural/velocity features are neutralized by
giving the synthesized manifest a normal create→submit gap (documented honesty point).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from services.risk.app import db, profiles
from services.risk.app.auth import current_user
from services.risk.app.overlays import build_tamper_overlays

_DEFAULT_CASE_STORE = Path(__file__).resolve().parent.parent / "case_store"
# Accepted purposes. "loan" is kept as a back-compat alias for "salaried_loan".
_PURPOSES = {"kyc", "salaried_loan", "other"}
_PURPOSE_ALIASES = {"loan": "salaried_loan"}

router = APIRouter(tags=["cases"])


@router.get("/cases/profiles")
def get_profiles() -> dict:
    """Purpose → document-slot catalogue that drives the dynamic upload form (one source of truth)."""
    return profiles.profiles_payload()


def _case_store() -> Path:
    """Resolved case-store dir — read from env at call time (test-friendly)."""
    return Path(os.environ.get("TRUSTSHIELD_CASE_STORE", str(_DEFAULT_CASE_STORE)))


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name) or "file"


def _build_manifest(case_id: str, applicant_name, ground_truth, doc_records) -> dict:
    """Synthesize a packet manifest with NEUTRAL timestamps (no real velocity signal)."""
    now = datetime.now(timezone.utc)
    created = now - timedelta(hours=168)  # ~1 week → neutral, clean-like velocity
    return {
        "packet_id": case_id,
        "applicant_name": applicant_name,
        "created_at": created.isoformat(),
        "submitted_at": now.isoformat(),
        "documents": doc_records,
        "ground_truth": ground_truth,
    }


@router.post("/cases")
def submit_case(
    purpose: str = Form(default="other"),
    loan_amount: Optional[float] = Form(default=None),
    tenure_months: Optional[int] = Form(default=None),
    existing_emi: Optional[float] = Form(default=None),
    doc_types: list[str] = Form(default=[]),  # per-file slot hint, parallel to `files`
    files: list[UploadFile] = File(...),
    user: dict = Depends(current_user),
) -> dict:
    """User submits a packet: save → ingest each doc → score → verify → persist → return summary.

    `doc_types[i]` is the slot the user dropped `files[i]` into (e.g. "pan", "form16"); it becomes
    the ingest hint so we don't depend on the classifier for a user-asserted document. When absent
    the classifier infers the type (back-compat / API callers).
    """
    from services.forensics.app.ingest.pipeline import ingest_document
    from services.risk.app.aggregator import apply_verification, score_packet_dir
    from services.risk.app.underwriting import build_verification

    purpose = _PURPOSE_ALIASES.get(purpose, purpose)
    if purpose not in _PURPOSES:
        purpose = "other"
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")
    hints = list(doc_types) if doc_types else []

    case_id = f"case_{uuid.uuid4().hex[:12]}"
    case_dir = _case_store() / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    doc_records: list[dict] = []      # for the manifest (schema doc_type)
    ingested: list[dict] = []         # per-doc display (fine doc_type + fields + kyc)
    applicant_name = None
    applicant_pan = None
    employer = None

    for i, f in enumerate(files):
        if not f.filename:
            continue
        content = f.file.read()
        if not content:
            continue
        fname = _safe_name(f.filename)
        (case_dir / fname).write_bytes(content)

        hint = hints[i].strip() if i < len(hints) and hints[i] else None
        ing = ingest_document(str(case_dir / fname), doc_type=hint)
        ingested.append({"filename": fname, "slot": hint, **ing})
        if not ing.get("ok"):
            continue
        fields = ing.get("fields", {})
        schema_dt = ing.get("schema_doc_type", "other")
        doc_records.append({"filename": fname, "doc_type": schema_dt})
        applicant_name = applicant_name or fields.get("name") or fields.get("owner_name")
        applicant_pan = applicant_pan or fields.get("pan")
        employer = employer or fields.get("employer")

    ground_truth = {"applicant_pan": applicant_pan, "employer": employer}
    if loan_amount is not None:
        ground_truth["loan_amount"] = float(loan_amount)

    manifest = _build_manifest(case_id, applicant_name, ground_truth, doc_records)
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Authenticity score (reuses Phase 1→4 pipeline). Graph omitted for single real uploads.
    try:
        decision = score_packet_dir(case_dir, case_id, graph=None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"scoring failed: {exc}") from exc

    # KYC + underwriting verification (separate eligibility axis; consistency findings fold in).
    verification = build_verification(
        purpose, ingested, loan_amount=loan_amount,
        tenure_months=tenure_months, existing_emi=existing_emi,
    )
    decision = apply_verification(
        decision, verification["findings"], verification["trust_penalty"]
    )
    # Serialize the verification block (drop the EvidenceItem objects — they're now in the chain).
    verification_out = {k: v for k, v in verification.items() if k != "findings"}

    overlays = build_tamper_overlays(case_dir, decision)
    decision_dump = decision.model_dump(mode="json")
    action = decision.recommendation.action.value
    trust = decision.trust_score.overall

    db.create_case(
        case_id=case_id, user_id=user["uid"], user_email=user["email"], purpose=purpose,
        status="scored", trust_score=trust, action=action,
        decision_json=json.dumps(decision_dump), overlays_json=json.dumps(overlays),
        verification_json=json.dumps(verification_out),
        loan_amount=loan_amount, tenure_months=tenure_months,
    )
    for d in ingested:
        if d.get("ok"):
            db.add_case_doc(case_id, d["filename"], d.get("doc_type"),
                            json.dumps(d.get("fields", {})), json.dumps(d.get("kyc", {})))
    return {
        "ok": True, "case_id": case_id, "purpose": purpose,
        "trust_score": trust, "action": action,
        "documents": [
            {"filename": d["filename"], "slot": d.get("slot"), "doc_type": d.get("doc_type"),
             "fields": d.get("fields", {}), "kyc": d.get("kyc", {})}
            for d in ingested
        ],
        "verification": verification_out,
        "decision": decision_dump,
        "tamper_overlays": overlays,
    }


@router.get("/cases")
def list_cases(user: dict = Depends(current_user)) -> dict:
    """Admin: all cases. User: own cases."""
    uid = None if user.get("role") == "admin" else user["uid"]
    return {"cases": db.list_cases(user_id=uid), "role": user["role"]}


@router.get("/cases/{case_id}")
def get_case(case_id: str, user: dict = Depends(current_user)) -> dict:
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    if user.get("role") != "admin" and case.get("user_id") != user["uid"]:
        raise HTTPException(status_code=403, detail="not your case")
    case["decision"] = json.loads(case.pop("decision_json")) if case.get("decision_json") else None
    case["tamper_overlays"] = json.loads(case.pop("overlays_json")) if case.get("overlays_json") else []
    case["verification"] = json.loads(case.pop("verification_json")) if case.get("verification_json") else None
    return case
