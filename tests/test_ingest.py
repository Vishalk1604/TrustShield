"""Tests for the real-document ingestion core (plan.md §7, Week 1):
normalization + identifier validators + the heuristic doc-type classifier.

Dependency-free — runs on any machine (no OCR/GPU needed).
"""

from services.forensics.app.ingest.normalize import (
    parse_amount,
    parse_date,
    validate_aadhaar,
    validate_ifsc,
    validate_pan,
    verhoeff_generate,
    verhoeff_validate,
)
from services.forensics.app.ingest.classify import classify_document, to_schema_doctype


# --------------------------------------------------------------------------
# Money / date parsing
# --------------------------------------------------------------------------

def test_parse_amount_indian_formats():
    assert parse_amount("Rs. 1,45,000") == 145000.0
    assert parse_amount("₹12,34,567") == 1234567.0
    assert parse_amount("INR 9,50,000.50") == 950000.50
    assert parse_amount("5 lakh") == 500000.0
    assert parse_amount("1.2 crore") == 12000000.0
    assert parse_amount("2 Lakhs") == 200000.0
    assert parse_amount("no number here") is None
    assert parse_amount(None) is None


def test_parse_date_formats():
    assert parse_date("15/01/2024") == "2024-01-15"
    assert parse_date("15-01-2024") == "2024-01-15"
    assert parse_date("15-Jan-2024") == "2024-01-15"
    assert parse_date("15 January 2024") == "2024-01-15"
    assert parse_date("2024-01-15") == "2024-01-15"
    assert parse_date("Issued on 15/01/2024 by bank") == "2024-01-15"
    assert parse_date("garbage") is None


# --------------------------------------------------------------------------
# Verhoeff (self-consistent — independent of any external vector)
# --------------------------------------------------------------------------

def test_verhoeff_self_consistency():
    for base in ("12345678901", "99994105705", "53261411600", "20000000000"):
        cd = verhoeff_generate(base)
        full = base + str(cd)
        assert verhoeff_validate(full), f"{full} should validate"
        # Tampering any single digit must break the checksum.
        tampered = base + str((cd + 1) % 10)
        assert not verhoeff_validate(tampered)


# --------------------------------------------------------------------------
# PAN
# --------------------------------------------------------------------------

def test_validate_pan():
    r = validate_pan("abcpv1234d")           # lowercase normalised
    assert r["valid"] and r["normalized"] == "ABCPV1234D"
    assert r["holder_type"] == "Individual"   # 4th char 'P'
    assert validate_pan("ABCCV1234D")["holder_type"] == "Company"  # 'C'
    assert not validate_pan("ABC1234D")["valid"]                   # bad structure
    assert not validate_pan("ABCQV1234D")["valid"]                 # 'Q' not a holder type
    assert not validate_pan("")["valid"]


# --------------------------------------------------------------------------
# Aadhaar (full vs masked)
# --------------------------------------------------------------------------

def test_validate_aadhaar_full_checksum():
    base = "99994105705"                      # 11 digits (does not start 0/1)
    full = base + str(verhoeff_generate(base))
    r = validate_aadhaar(full)
    assert r["valid"] and r["checksum_verified"] and not r["masked"]
    # Break the checksum.
    bad = base + str((verhoeff_generate(base) + 1) % 10)
    assert not validate_aadhaar(bad)["valid"]


def test_validate_aadhaar_masked():
    r = validate_aadhaar("XXXXXXXX1234")
    assert r["valid"] and r["masked"] and not r["checksum_verified"]
    r2 = validate_aadhaar("**** **** 1234")
    assert r2["masked"] and not r2["checksum_verified"]
    assert not validate_aadhaar("1234")["valid"]            # too short
    assert not validate_aadhaar("012345678901")["valid"]    # starts with 0


# --------------------------------------------------------------------------
# IFSC
# --------------------------------------------------------------------------

def test_validate_ifsc():
    r = validate_ifsc("hdfc0001234")
    assert r["valid"] and r["normalized"] == "HDFC0001234" and r["bank_code"] == "HDFC"
    assert not validate_ifsc("HDFC1234567")["valid"]   # 5th char must be '0'
    assert not validate_ifsc("HDF0001234")["valid"]    # only 3 letters
    assert not validate_ifsc("")["valid"]


# --------------------------------------------------------------------------
# Doc-type classifier
# --------------------------------------------------------------------------

def test_classify_financial_and_kyc():
    cases = {
        "form16": "FORM NO. 16\nCertificate under section 203\nGross Salary ... TDS",
        "salary_slip": "SALARY SLIP\nBasic Pay 50000\nHRA\nNet Pay 90000\nDeductions",
        "bank_statement": "Statement of Account\nIFSC: HDFC0001234\nClosing Balance\nUPI",
        "pan": "INCOME TAX DEPARTMENT\nPermanent Account Number Card\nPAN ABCPV1234D",
        "aadhaar": "Government of India\nUnique Identification Authority of India (UIDAI)\nAadhaar",
    }
    for expected, text in cases.items():
        out = classify_document(text)
        assert out["doc_type"] == expected, f"{expected}: got {out}"
        assert out["confidence"] > 0.0


def test_classify_unknown_is_other():
    out = classify_document("random unrelated text with no document keywords")
    assert out["doc_type"] == "other" and out["confidence"] == 0.0


def test_kyc_types_map_to_identity():
    assert to_schema_doctype("pan") == "identity"
    assert to_schema_doctype("aadhaar") == "identity"
    assert to_schema_doctype("form16") == "form16"
