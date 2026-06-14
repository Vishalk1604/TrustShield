"""Phase 2 — Semantic rules engine tests.

Tests:
- Entity extraction spot-check on ≥5 different packet types.
- Every cross-document inconsistency packet raises a semantic finding.
- Clean packets raise 0 semantic findings.
- Property checks: owner vs applicant, property ID consistency, LTV, EC vs CERSAI.
- Every finding is a valid EvidenceItem (category=semantic).

Run from the repo root: pytest tests/test_rules.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKETS_DIR = ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = ROOT / "data" / "synthetic" / "labels.json"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def labels() -> dict:
    if not LABELS_PATH.exists():
        pytest.skip("Run python -m data.generator.generate first")
    return json.loads(LABELS_PATH.read_text())


@pytest.fixture(scope="session")
def extractor():
    from services.forensics.app.extractor import extract_entities
    return extract_entities


@pytest.fixture(scope="session")
def run_rules():
    from services.risk.app.rules import run_all_rules
    return run_all_rules


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _docs_in(pkt_dir: Path) -> list[dict]:
    mf = pkt_dir / "manifest.json"
    if not mf.exists():
        return []
    return json.loads(mf.read_text()).get("documents", [])


def _manifest(pkt_dir: Path) -> dict:
    mf = pkt_dir / "manifest.json"
    return json.loads(mf.read_text()) if mf.exists() else {}


def _loan_amount_from_manifest(pkt_dir: Path) -> Optional[float]:
    mf = _manifest(pkt_dir)
    claims = mf.get("ground_truth", {}).get("claims", {})
    for fname, claim in claims.items():
        if "loan_amount" in claim:
            return float(claim["loan_amount"])
    return None


def _pan_from_manifest(pkt_dir: Path) -> Optional[str]:
    mf = _manifest(pkt_dir)
    return mf.get("ground_truth", {}).get("applicant_pan")


def _extract_all(pkt_dir: Path, extractor) -> dict[str, dict]:
    """Extract entities from every document in the packet. Returns {doc_type: entities}."""
    result: dict[str, dict] = {}
    for doc_rec in _docs_in(pkt_dir):
        doc_path = pkt_dir / doc_rec["filename"]
        if not doc_path.exists():
            continue
        ent = extractor(str(doc_path), doc_rec.get("doc_type", "other"))
        result[doc_rec["doc_type"]] = ent
    return result


# --------------------------------------------------------------------------
# Extraction spot-check
# --------------------------------------------------------------------------

def test_extraction_form16(labels: dict, extractor) -> None:
    """Form 16 extraction: name, PAN, employer, income, tax all present for clean packets."""
    count = 0
    for pkt_id, entry in labels.items():
        if entry.get("label") != "clean":
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        form16_path = pkt_dir / "form16.pdf"
        if not form16_path.exists():
            continue
        ent = extractor(str(form16_path), "form16")
        assert ent.get("name"), f"{pkt_id} form16 missing name"
        assert ent.get("pan"), f"{pkt_id} form16 missing PAN"
        assert ent.get("employer"), f"{pkt_id} form16 missing employer"
        assert ent.get("gross_income") is not None, f"{pkt_id} form16 missing gross_income"
        assert ent.get("gross_income") > 0, f"{pkt_id} form16 gross_income = 0"
        assert ent.get("tax_paid") is not None, f"{pkt_id} form16 missing tax_paid"
        count += 1
        if count >= 5:
            break
    assert count >= 5, f"Spot-checked only {count} form16 packets"


def test_extraction_bank_statement(labels: dict, extractor) -> None:
    """Bank statement: name, salary_credits list non-empty, implied_annual positive."""
    count = 0
    for pkt_id, entry in labels.items():
        if entry.get("label") != "clean":
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        bs_path = pkt_dir / "bank_statement.pdf"
        if not bs_path.exists():
            continue
        ent = extractor(str(bs_path), "bank_statement")
        assert ent.get("name"), f"{pkt_id} bank_statement missing name"
        assert ent.get("salary_credits"), f"{pkt_id} bank_statement missing salary_credits"
        assert ent.get("implied_annual", 0) > 0, f"{pkt_id} implied_annual <= 0"
        count += 1
        if count >= 5:
            break
    assert count >= 5


def test_extraction_sale_deed(labels: dict, extractor) -> None:
    """Sale deed: property_id, owner_name, address, PAN all present."""
    count = 0
    for pkt_id, entry in labels.items():
        pkt_dir = PACKETS_DIR / pkt_id
        sd_path = pkt_dir / "sale_deed.pdf"
        if not sd_path.exists():
            continue
        ent = extractor(str(sd_path), "sale_deed")
        assert ent.get("property_id"), f"{pkt_id} sale_deed missing property_id"
        assert ent.get("owner_name"), f"{pkt_id} sale_deed missing owner_name"
        count += 1
        if count >= 5:
            break
    assert count >= 5, f"Only {count} sale_deed docs found"


def test_extraction_encumbrance_certificate(labels: dict, extractor) -> None:
    """EC: property_id, owner_name, claims_nil present."""
    count = 0
    for pkt_id, entry in labels.items():
        pkt_dir = PACKETS_DIR / pkt_id
        ec_path = pkt_dir / "encumbrance_certificate.pdf"
        if not ec_path.exists():
            continue
        ent = extractor(str(ec_path), "encumbrance_certificate")
        assert ent.get("property_id"), f"{pkt_id} EC missing property_id"
        assert ent.get("owner_name"), f"{pkt_id} EC missing owner_name"
        assert "claims_nil" in ent, f"{pkt_id} EC missing claims_nil field"
        count += 1
        if count >= 5:
            break
    assert count >= 5


def test_extraction_property_valuation(labels: dict, extractor) -> None:
    """Property valuation: property_id, valuation_amount positive."""
    count = 0
    for pkt_id, entry in labels.items():
        pkt_dir = PACKETS_DIR / pkt_id
        pv_path = pkt_dir / "property_valuation.pdf"
        if not pv_path.exists():
            continue
        ent = extractor(str(pv_path), "property_valuation")
        assert ent.get("property_id"), f"{pkt_id} valuation missing property_id"
        assert ent.get("valuation_amount") is not None, f"{pkt_id} valuation missing amount"
        assert ent.get("valuation_amount", 0) > 0
        count += 1
        if count >= 5:
            break
    assert count >= 5


# --------------------------------------------------------------------------
# Financial rules
# --------------------------------------------------------------------------

def test_cross_doc_inconsistency_packets_flagged(labels: dict, extractor, run_rules) -> None:
    """Every cross_document_inconsistency packet must produce ≥1 semantic finding."""
    flagged = 0
    missed: list[str] = []

    for pkt_id, entry in labels.items():
        if "cross_document_inconsistency" not in entry.get("fraud_types", []):
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        entities = _extract_all(pkt_dir, extractor)
        pan = _pan_from_manifest(pkt_dir)
        items = run_rules(entities, loan_amount=None, applicant_pan=pan)
        if items:
            flagged += 1
        else:
            missed.append(pkt_id)

    assert not missed, f"cross_doc inconsistency packets with no semantic findings: {missed}"
    assert flagged > 0


def test_clean_packets_have_no_semantic_findings(labels: dict, extractor, run_rules) -> None:
    """Clean packets must produce 0 semantic findings."""
    for pkt_id, entry in labels.items():
        if entry.get("label") != "clean":
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        entities = _extract_all(pkt_dir, extractor)
        pan = _pan_from_manifest(pkt_dir)
        loan = _loan_amount_from_manifest(pkt_dir)
        items = run_rules(entities, loan_amount=loan, applicant_pan=pan)
        assert not items, (
            f"Unexpected semantic findings on clean packet {pkt_id}: "
            f"{[i.title for i in items]}"
        )


def test_income_bank_mismatch_detected() -> None:
    """Direct unit test: significant income-bank mismatch is flagged."""
    from services.risk.app.rules import check_income_vs_bank

    form16 = {"gross_income": 1_820_000}
    bank = {"implied_annual": 820_000}  # ~55% gap
    items = check_income_vs_bank(form16, bank)
    assert items, "Expected income-bank mismatch finding"
    assert any("bank" in i.title.lower() or "income" in i.title.lower() for i in items)


def test_income_bank_match_not_flagged() -> None:
    """Clean income (net after tax) vs bank credits is within tolerance."""
    from services.risk.app.rules import check_income_vs_bank

    # Clean: gross 1,820,000; net (after ~10% tax) = 1,638,000
    form16 = {"gross_income": 1_820_000}
    bank = {"implied_annual": 1_638_000}
    items = check_income_vs_bank(form16, bank)
    assert not items, f"Unexpected income-bank flag for clean case: {[i.title for i in items]}"


# --------------------------------------------------------------------------
# Property / legal rules
# --------------------------------------------------------------------------

def test_property_id_consistency_mismatch_detected(labels: dict, extractor, run_rules) -> None:
    """property_mismatch packet must raise a property-ID inconsistency finding."""
    for pkt_id, entry in labels.items():
        if "property_mismatch" not in entry.get("fraud_types", []):
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        entities = _extract_all(pkt_dir, extractor)
        pan = _pan_from_manifest(pkt_dir)
        items = run_rules(entities, applicant_pan=pan)
        titles = [i.title for i in items]
        assert any("property" in t.lower() and "inconsist" in t.lower() for t in titles), (
            f"Expected property ID inconsistency finding on {pkt_id}, got: {titles}"
        )
        return
    pytest.fail("No property_mismatch packet in labels.json")


def test_ec_vs_cersai_tampered_ec_flagged(labels: dict, extractor, run_rules) -> None:
    """tampered_encumbrance packet: CERSAI has charge but EC claims NIL → semantic finding."""
    for pkt_id, entry in labels.items():
        if "tampered_encumbrance" not in entry.get("fraud_types", []):
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        entities = _extract_all(pkt_dir, extractor)
        pan = _pan_from_manifest(pkt_dir)
        items = run_rules(entities, applicant_pan=pan)
        titles = [i.title for i in items]
        assert any("cersai" in t.lower() or "encumbrance" in t.lower() for t in titles), (
            f"Expected EC-vs-CERSAI finding on {pkt_id}, got: {titles}"
        )
        return
    pytest.fail("No tampered_encumbrance packet in labels.json")


def test_valuation_inflation_ltv_flagged(labels: dict, extractor, run_rules) -> None:
    """valuation_inflation packet: loan > valuation → LTV > 100% → CRITICAL finding."""
    for pkt_id, entry in labels.items():
        if "valuation_inflation" not in entry.get("fraud_types", []):
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        entities = _extract_all(pkt_dir, extractor)
        loan = _loan_amount_from_manifest(pkt_dir)
        pan = _pan_from_manifest(pkt_dir)
        assert loan is not None, f"loan_amount missing from manifest of {pkt_id}"
        items = run_rules(entities, loan_amount=loan, applicant_pan=pan)
        titles = [i.title for i in items]
        assert any("ltv" in t.lower() or "loan-to-value" in t.lower() for t in titles), (
            f"Expected LTV finding on valuation_inflation {pkt_id}, got: {titles}"
        )
        return
    pytest.fail("No valuation_inflation packet in labels.json")


def test_property_mismatch_clean_secured_no_flag(labels: dict, extractor, run_rules) -> None:
    """Clean secured loans must not trigger property ID or LTV flags."""
    for pkt_id, entry in labels.items():
        if entry.get("label") != "clean":
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        # Only check packets that have sale_deed (secured loans)
        if not (pkt_dir / "sale_deed.pdf").exists():
            continue
        entities = _extract_all(pkt_dir, extractor)
        pan = _pan_from_manifest(pkt_dir)
        loan = _loan_amount_from_manifest(pkt_dir)
        items = run_rules(entities, loan_amount=loan, applicant_pan=pan)
        assert not items, (
            f"Unexpected semantic findings on clean secured {pkt_id}: "
            f"{[i.title for i in items]}"
        )


def test_every_finding_is_semantic_evidence_item(labels: dict, extractor, run_rules) -> None:
    """All findings must deserialize into valid EvidenceItems with category=semantic."""
    from shared.schemas import EvidenceItem

    hit = False
    for pkt_id, entry in labels.items():
        ft = set(entry.get("fraud_types", []))
        if not (ft & {"cross_document_inconsistency", "property_mismatch",
                      "tampered_encumbrance", "valuation_inflation"}):
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        entities = _extract_all(pkt_dir, extractor)
        pan = _pan_from_manifest(pkt_dir)
        loan = _loan_amount_from_manifest(pkt_dir)
        items = run_rules(entities, loan_amount=loan, applicant_pan=pan)
        for item in items:
            assert item.category.value == "semantic", f"Wrong category: {item.category}"
            assert item.description, "Empty description"
            assert item.title, "Empty title"
            hit = True
    assert hit, "No semantic findings found to validate"


# --------------------------------------------------------------------------
# EC vs CERSAI unit tests
# --------------------------------------------------------------------------

def test_ec_cersai_rule_fires_when_nil_and_charges() -> None:
    """Unit test: EC says NIL, CERSAI has charges → finding."""
    from services.risk.app.rules import check_ec_vs_cersai

    # GHJPR3456M = Sneha Reddy; CERSAI has HDFC Bank charge on SY-058/1A
    items = check_ec_vs_cersai(
        ec={"claims_nil": True},
        applicant_pan="GHJPR3456M",
        property_id="SY-058/1A",
    )
    assert items, "Expected EC-vs-CERSAI finding"
    assert items[0].category.value == "semantic"
    assert items[0].severity.value == "critical"


def test_ec_cersai_rule_silent_when_cersai_clear() -> None:
    """EC says NIL, CERSAI is clear → no finding."""
    from services.risk.app.rules import check_ec_vs_cersai

    # ABMPS1234F = Rahul Sharma; CERSAI says clear
    items = check_ec_vs_cersai(
        ec={"claims_nil": True},
        applicant_pan="ABMPS1234F",
        property_id="SY-217/3B",
    )
    assert not items, f"Unexpected EC-vs-CERSAI finding: {items}"


def test_ec_cersai_rule_silent_when_ec_discloses_charges() -> None:
    """EC shows charges, CERSAI has charges → no rule violation (consistent)."""
    from services.risk.app.rules import check_ec_vs_cersai

    items = check_ec_vs_cersai(
        ec={"claims_nil": False},
        applicant_pan="GHJPR3456M",
        property_id="SY-058/1A",
    )
    assert not items, "Should not flag when EC discloses the charges"


# --------------------------------------------------------------------------
# LTV unit tests
# --------------------------------------------------------------------------

def test_ltv_above_90_flagged() -> None:
    from services.risk.app.rules import check_ltv

    items = check_ltv({"valuation_amount": 10_000_000}, loan_amount=9_500_000)
    assert items, "Expected LTV flag"
    assert items[0].values["ltv"] == pytest.approx(0.95, rel=0.01)


def test_ltv_above_100_is_critical() -> None:
    from services.risk.app.rules import check_ltv

    items = check_ltv({"valuation_amount": 7_500_000}, loan_amount=9_500_000)
    assert items
    assert items[0].severity.value == "critical"


def test_ltv_below_90_not_flagged() -> None:
    from services.risk.app.rules import check_ltv

    items = check_ltv({"valuation_amount": 9_000_000}, loan_amount=6_000_000)
    assert not items, f"Unexpected LTV flag: {items}"
