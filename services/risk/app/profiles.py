"""Purpose → required-document profiles (plan §9).

A bank asks for a *specific* document set depending on what the applicant wants (open-KYC vs a
salaried personal loan). This module is the single source of truth for:
  - which documents a purpose requires/accepts (drives the completeness check in `underwriting`),
  - the named slots the upload form renders (served to the frontend via `GET /cases/profiles`).

Slot keys are the *fine* doc-type hints fed to `ingest_document(path, doc_type=<key>)` so we don't
rely on the classifier for a user-asserted document. Pure data; no I/O, no network.

Scope now: KYC + salaried personal loan (plan-locked). Home-loan/LAP collateral and self-employed
tiers are documented as later additions.
"""

from __future__ import annotations

# Per-slot metadata. `schema_doc_type` is the shared `DocType` value used in the scored manifest;
# several fine slots collapse to one schema type (pan + aadhaar → identity).
SLOTS: dict[str, dict] = {
    "pan": {
        "label": "PAN card",
        "schema_doc_type": "identity",
        "multiple": False,
        "category": "poi",  # proof of identity
        "hint": "Proof of identity (mandatory for financial KYC). Photo or PDF.",
    },
    "aadhaar": {
        "label": "Aadhaar (masked)",
        "schema_doc_type": "identity",
        "multiple": False,
        "category": "poi_poa",  # serves as both POI and POA
        "hint": "Upload the MASKED Aadhaar only. Serves as identity + address proof.",
    },
    "address_proof": {
        "label": "Address proof",
        "schema_doc_type": "address_proof",
        "multiple": False,
        "category": "poa",  # proof of address
        "hint": "Utility bill (≤2 months) / passport / voter ID / driving licence.",
    },
    "salary_slip": {
        "label": "Salary slips (last 3 months)",
        "schema_doc_type": "salary_slip",
        "multiple": True,
        "category": "income",
        "hint": "PDF payslips — upload up to 3 recent months.",
    },
    "form16": {
        "label": "Form 16",
        "schema_doc_type": "form16",
        "multiple": False,
        "category": "income",
        "hint": "Employer TDS certificate (Part A+B), e.g. from TRACES.",
    },
    "bank_statement": {
        "label": "Bank statement (6 months)",
        "schema_doc_type": "bank_statement",
        "multiple": False,
        "category": "income",
        "hint": "Salary-account statement PDF (password-protected is fine).",
    },
    "itr": {
        "label": "ITR / 26AS / AIS",
        "schema_doc_type": "itr",
        "multiple": False,
        "category": "income",
        "hint": "Optional — income-tax return or annual statement.",
    },
}

# Purpose → {label, required slot keys, optional slot keys, needs_loan_terms}.
PROFILES: dict[str, dict] = {
    "kyc": {
        "label": "KYC verification",
        "required": ["pan", "aadhaar", "address_proof"],
        "optional": [],
        "needs_loan_terms": False,
    },
    "salaried_loan": {
        "label": "Salaried personal loan",
        "required": ["pan", "aadhaar", "address_proof", "salary_slip", "form16", "bank_statement"],
        "optional": ["itr"],
        "needs_loan_terms": True,
    },
}

# Document categories used by the KYC verifier.
POI_SLOTS = {"pan", "aadhaar"}            # proof of identity
POA_SLOTS = {"aadhaar", "address_proof"}  # proof of address


def known_purpose(purpose: str) -> bool:
    return purpose in PROFILES


def profile_for(purpose: str) -> dict | None:
    return PROFILES.get(purpose)


def slot_schema_doctype(slot_key: str) -> str:
    """The shared DocType value for a slot key (fallback: the key itself)."""
    meta = SLOTS.get(slot_key)
    return (meta or {}).get("schema_doc_type", slot_key)


def profiles_payload() -> dict:
    """JSON-serializable profile + slot catalogue for the upload form (one source of truth)."""
    out: dict = {"purposes": []}
    for key, prof in PROFILES.items():
        slots = []
        for sk in [*prof["required"], *prof["optional"]]:
            meta = SLOTS[sk]
            slots.append({
                "key": sk,
                "label": meta["label"],
                "hint": meta["hint"],
                "multiple": meta["multiple"],
                "required": sk in prof["required"],
            })
        out["purposes"].append({
            "key": key,
            "label": prof["label"],
            "needs_loan_terms": prof["needs_loan_terms"],
            "slots": slots,
        })
    return out
