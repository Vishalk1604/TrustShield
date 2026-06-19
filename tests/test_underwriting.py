"""KYC + underwriting verification (plan §9): profiles, completeness, KYC, income
reconciliation, affordability/FOIR, the trust-penalty fold-in, and address-proof
classify/extract. Pure functions — no server, no DB."""

from services.forensics.app.extractor import _EXTRACTORS, extract_entities  # noqa: F401
from services.forensics.app.ingest.classify import classify_document, to_schema_doctype
from services.forensics.app.ingest.extract import extract_fields
from services.risk.app import profiles, underwriting
from services.risk.app.aggregator import aggregate, apply_verification
from shared.schemas import DocType


# ── a complete, clean salaried-loan applicant ────────────────────────────────────
def _salaried_set():
    return [
        {"ok": True, "filename": "pan.pdf", "doc_type": "pan", "schema_doc_type": "identity",
         "fields": {"name": "RAHUL SHARMA", "pan": "ABCPS1234F"},
         "kyc": {"pan": {"valid": True}}},
        {"ok": True, "filename": "aadhaar.pdf", "doc_type": "aadhaar", "schema_doc_type": "identity",
         "fields": {"name": "Rahul Sharma"},
         "kyc": {"aadhaar": {"valid": True, "masked": True}}},
        {"ok": True, "filename": "poa.pdf", "doc_type": "address_proof",
         "schema_doc_type": "address_proof",
         "fields": {"name": "Rahul Sharma", "address": "MG Road, Bengaluru"}, "kyc": {}},
        {"ok": True, "filename": "slip.pdf", "doc_type": "salary_slip",
         "schema_doc_type": "salary_slip",
         "fields": {"name": "Rahul Sharma", "net_monthly": 80000.0, "employer": "TCS"}, "kyc": {}},
        {"ok": True, "filename": "f16.pdf", "doc_type": "form16", "schema_doc_type": "form16",
         "fields": {"name": "Rahul Sharma", "pan": "ABCPS1234F", "gross_income": 1200000.0,
                    "employer": "TCS"}, "kyc": {}},
        {"ok": True, "filename": "bank.pdf", "doc_type": "bank_statement",
         "schema_doc_type": "bank_statement",
         "fields": {"name": "Rahul Sharma", "monthly_credit": 80000.0,
                    "implied_annual": 960000.0}, "kyc": {}},
    ]


# ── profiles ──────────────────────────────────────────────────────────────────────
def test_profiles_payload_shape():
    payload = profiles.profiles_payload()
    keys = {p["key"] for p in payload["purposes"]}
    assert {"kyc", "salaried_loan"} <= keys
    sl = next(p for p in payload["purposes"] if p["key"] == "salaried_loan")
    assert sl["needs_loan_terms"] is True
    slot_keys = {s["key"] for s in sl["slots"]}
    assert {"pan", "aadhaar", "address_proof", "salary_slip", "form16", "bank_statement"} <= slot_keys
    # KYC requires no loan terms
    kyc = next(p for p in payload["purposes"] if p["key"] == "kyc")
    assert kyc["needs_loan_terms"] is False


# ── completeness ────────────────────────────────────────────────────────────────
def test_completeness_complete_and_missing():
    res, find = underwriting.check_completeness("salaried_loan", _salaried_set())
    assert res["complete"] is True and res["missing"] == [] and find == []

    res2, find2 = underwriting.check_completeness("kyc", [_salaried_set()[0]])  # only PAN
    assert res2["complete"] is False
    assert set(res2["missing"]) == {"aadhaar", "address_proof"}
    assert len(find2) == 2 and all(f.category.value == "semantic" for f in find2)


# ── KYC ────────────────────────────────────────────────────────────────────────
def test_kyc_established_and_name_mismatch():
    kyc, find = underwriting.verify_kyc(_salaried_set())
    assert kyc["identity_established"] and kyc["address_established"] and kyc["name_consistent"]
    assert kyc["verdict"] == "ESTABLISHED" and find == []

    docs = _salaried_set()
    docs[1] = {**docs[1], "fields": {"name": "Someone Else"}}  # aadhaar name differs
    kyc2, find2 = underwriting.verify_kyc(docs)
    assert kyc2["name_consistent"] is False and kyc2["verdict"] == "INCOMPLETE"
    assert any("mismatch" in f.title.lower() for f in find2)


def test_kyc_identity_not_established_when_pan_invalid():
    docs = [{"ok": True, "filename": "pan.pdf", "doc_type": "pan", "schema_doc_type": "identity",
             "fields": {"pan": "BAD"}, "kyc": {"pan": {"valid": False}}}]
    kyc, find = underwriting.verify_kyc(docs)
    assert kyc["identity_established"] is False
    assert any(f.title == "Identity not established" for f in find)


# ── income reconciliation ─────────────────────────────────────────────────────────
def test_income_reconciles_and_flags_overstatement():
    income, find = underwriting.reconcile_income(_salaried_set())
    assert income["applicable"] and income["reconciled"] is True and find == []

    docs = _salaried_set()
    # Declared gross 50L but only ~9.6L banked → "declared gross far above banked" (LOW)
    docs[4] = {**docs[4], "fields": {**docs[4]["fields"], "gross_income": 5000000.0}}
    income2, find2 = underwriting.reconcile_income(docs)
    assert income2["reconciled"] is False
    assert any("gross" in f.title.lower() for f in find2)


# ── affordability / FOIR ───────────────────────────────────────────────────────────
def test_affordability_eligible_refer_decline():
    docs = _salaried_set()  # net 80k/mo
    elig = underwriting.assess_affordability(docs, requested_amount=1_500_000, tenure_months=60)
    assert elig["verdict"] == "ELIGIBLE" and elig["foir"] <= underwriting.FOIR_CAP
    assert elig["max_eligible_amount"] > 0

    decline = underwriting.assess_affordability(docs, requested_amount=9_000_000, tenure_months=36)
    assert decline["verdict"] == "DECLINE" and decline["foir"] > underwriting.FOIR_REFER_CAP

    # no requested amount → INFO with an indicative max
    info = underwriting.assess_affordability(docs, requested_amount=None, tenure_months=60)
    assert info["verdict"] == "INFO" and info["max_eligible_amount"] > 0


def test_affordability_not_applicable_without_income():
    elig = underwriting.assess_affordability([_salaried_set()[0]], 100000, 60)  # only PAN
    assert elig["applicable"] is False


# ── orchestration + trust fold-in ──────────────────────────────────────────────────
def test_build_verification_penalty_capped_and_eligibility_present():
    clean = underwriting.build_verification("salaried_loan", _salaried_set(),
                                            loan_amount=1_500_000, tenure_months=60)
    assert clean["trust_penalty"] == 0 and clean["findings"] == []
    assert clean["eligibility"]["verdict"] == "ELIGIBLE"

    sparse = underwriting.build_verification("salaried_loan", [_salaried_set()[0]],
                                             loan_amount=1_500_000)
    # many missing docs, but the penalty is capped (never tanks authenticity)
    assert sparse["trust_penalty"] <= underwriting.VERIFICATION_PENALTY_CAP
    assert sparse["completeness"]["complete"] is False


def test_apply_verification_lowers_trust_and_extends_chain():
    base = aggregate(packet_id="pkt_x", forensic_items=[], semantic_items=[],
                     fraud_probability=0.0, anomaly_score=0.0)
    assert base.trust_score.overall > 90  # clean

    v = underwriting.build_verification("kyc", [_salaried_set()[0]])  # only PAN → findings
    updated = apply_verification(base, v["findings"], v["trust_penalty"])
    assert updated.trust_score.overall == round(base.trust_score.overall - v["trust_penalty"], 1)
    assert len(updated.evidence_chain) > len(base.evidence_chain)


# ── address proof (new doc type) ────────────────────────────────────────────────────
def test_address_proof_classify_and_extract():
    text = ("ELECTRICITY BILL\nConsumer Name: Rahul Sharma\n"
            "Service Address: 12 MG Road, Bengaluru 560001\nBill Date: 05/05/2026\n"
            "Units consumed: 240\n")
    c = classify_document(text)
    assert c["doc_type"] == "address_proof"
    assert to_schema_doctype("address_proof") == "address_proof"

    fields = extract_fields("address_proof", text)
    assert fields["doc_type"] == "address_proof"
    assert "Rahul Sharma" in (fields.get("name") or "")
    assert fields.get("address")


def test_schema_has_address_proof():
    assert DocType.ADDRESS_PROOF.value == "address_proof"
