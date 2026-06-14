"""Phase 1 forensics tests.

Loads every synthetic packet and runs the forensic analyzer against each document.
Checks:
  - Precision/recall vs labels.json: every packet with a PER-DOCUMENT forensic fraud type
    raises ≥1 finding on the affected document(s); clean packets + semantic/behavioral/graph
    fraud packets raise 0 forensic findings.
  - Template fingerprint: the 4 template-reuse ring packets share the same fingerprint on
    their form16 docs; clean packets differ from ring packets.

Run from the repo root: pytest tests/test_forensics.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKETS_DIR = ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = ROOT / "data" / "synthetic" / "labels.json"

# Fraud types whose signals are embedded IN THE PDF BYTES of the affected document —
# i.e., detectable by per-document forensic analysis in Phase 1.
CLEARLY_FORENSIC_TYPES = {
    "suspicious_metadata",    # producer = editing tool / huge mod-create gap
    "edited_income_figure",   # white-box rectangle over income text
    "font_inconsistency",     # serif font mixed into sans-serif body
    "copy_paste",             # duplicate image objects on same page
    "incremental_update",     # multiple %%EOF markers in raw bytes
    "forged_title",           # white-box rectangle over owner name on sale_deed
    "tampered_encumbrance",   # white-box rectangle over charge row on EC
}

# Fraud types that are cross-document / cross-packet signals; Phase 1 should NOT raise
# per-document findings for these.
CROSS_DOCUMENT_OR_BEHAVIORAL = {
    "behavioral_velocity",           # identical timestamps across docs / tight submission window
    "template_reuse",                # same template fingerprint across multiple packets
    "cross_document_inconsistency",  # income mismatch across Form16/bank/salary — semantic
    "valuation_inflation",           # inflated valuation figure — semantic
    "property_mismatch",             # different property IDs across docs — semantic
    "double_financing",              # same property in multiple packets — graph
}


def _is_per_doc_forensic(fraud_types: list[str]) -> bool:
    """True if this packet is expected to produce per-document forensic findings in Phase 1.

    timestamp_anomaly is per-document ONLY when it is NOT paired with behavioral_velocity:
    - behavioral_velocity + timestamp_anomaly = identical timestamps across docs (cross-doc signal)
    - timestamp_anomaly alone = future dates or reversed date ordering (per-doc metadata signal)
    """
    ft = set(fraud_types)
    if ft & CLEARLY_FORENSIC_TYPES:
        return True
    if "timestamp_anomaly" in ft and "behavioral_velocity" not in ft:
        return True
    return False


def _is_non_forensic(label: str, fraud_types: list[str]) -> bool:
    """True if this packet should have ZERO forensic findings in Phase 1."""
    if label == "clean":
        return True
    ft = set(fraud_types)
    # Purely cross-document / behavioral / graph — no per-doc forensic signal
    if ft and not (ft - CROSS_DOCUMENT_OR_BEHAVIORAL) and "timestamp_anomaly" not in ft:
        return True
    # Semantic fraud only (no PDF-level tampering)
    if ft == {"cross_document_inconsistency"}:
        return True
    if ft == {"valuation_inflation"}:
        return True
    if ft == {"property_mismatch"}:
        return True
    if ft == {"double_financing"}:
        return True
    # behavioral_velocity + timestamp_anomaly = identical timestamps across docs (behavioral)
    if ft == {"behavioral_velocity", "timestamp_anomaly"}:
        return True
    return False


@pytest.fixture(scope="session")
def labels() -> dict:
    if not LABELS_PATH.exists():
        pytest.skip("Synthetic packets not generated yet — run python -m data.generator.generate")
    return json.loads(LABELS_PATH.read_text())


@pytest.fixture(scope="session")
def analyzer():
    from services.forensics.app.analyzer import analyze_pdf
    return analyze_pdf


# ---------------------------------------------------------------------------
# Main precision/recall test
# ---------------------------------------------------------------------------

def test_forensics_precision_recall(labels: dict, analyzer) -> None:
    """Every packet with per-document forensic fraud raises ≥1 finding on its affected doc.
    Clean + non-forensic fraud packets produce 0 findings.
    """
    true_positives = 0
    false_negatives: list[str] = []
    false_positives: list[str] = []

    for pkt_id, entry in labels.items():
        pkt_dir = PACKETS_DIR / pkt_id
        fraud_types: list[str] = entry.get("fraud_types", [])
        label: str = entry.get("label", "clean")
        affected: list[str] = entry.get("affected_docs", [])

        expect_forensic = _is_per_doc_forensic(fraud_types)
        expect_none = _is_non_forensic(label, fraud_types)

        for doc_rec in _docs_in(pkt_dir):
            filename = doc_rec["filename"]
            doc_path = pkt_dir / filename
            if not doc_path.exists():
                continue
            result = analyzer(str(doc_path), doc_type=doc_rec.get("doc_type", "other"),
                              filename=filename)
            found = bool(result.get("findings"))

            if expect_forensic and filename in (affected or []):
                if found:
                    true_positives += 1
                else:
                    false_negatives.append(f"{pkt_id}/{filename} [{fraud_types}]")

            if expect_none and found:
                false_positives.append(
                    f"{pkt_id}/{filename}: {[f['title'] for f in result['findings']]}"
                )

    print(f"\nForensics: TP={true_positives}, FN={len(false_negatives)}, FP={len(false_positives)}")
    if false_negatives:
        print("  False negatives (missed):", false_negatives)
    if false_positives:
        print("  False positives (spurious):", false_positives)

    assert not false_negatives, f"Forensic fraud packets missed: {false_negatives}"
    assert not false_positives, f"Unexpected findings on clean/semantic packets: {false_positives}"
    assert true_positives > 0, "No true positives — analyzer may not be running"


def test_clean_packets_have_no_forensic_findings(labels: dict, analyzer) -> None:
    """All clean packets must produce zero forensic findings on every document."""
    for pkt_id, entry in labels.items():
        if entry.get("label") != "clean":
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        for doc_rec in _docs_in(pkt_dir):
            filename = doc_rec["filename"]
            doc_path = pkt_dir / filename
            if not doc_path.exists():
                continue
            result = analyzer(str(doc_path), doc_type=doc_rec.get("doc_type", "other"),
                              filename=filename)
            assert not result.get("findings"), (
                f"Unexpected finding on clean packet {pkt_id}/{filename}: "
                f"{[f['title'] for f in result['findings']]}"
            )


def test_template_fingerprint_collides_within_ring(labels: dict, analyzer) -> None:
    """The 4 template-reuse ring packets share the same fingerprint on form16.pdf
    (same producer 'QuickDocs Generator', same font/layout structure).
    Clean-packet form16 fingerprints must differ (different producer 'TrustShield SynthGen 1.0').
    """
    ring_fps: list[str] = []
    clean_fps: list[str] = []

    for pkt_id, entry in labels.items():
        pkt_dir = PACKETS_DIR / pkt_id
        fraud_types = entry.get("fraud_types", [])
        is_ring = "template_reuse" in fraud_types

        form16_path = pkt_dir / "form16.pdf"
        if not form16_path.exists():
            continue

        result = analyzer(str(form16_path), doc_type="form16", filename="form16.pdf")
        fp = result["template_fingerprint"]

        if is_ring:
            ring_fps.append(fp)
        elif entry.get("label") == "clean":
            clean_fps.append(fp)

    assert len(ring_fps) == 4, f"Expected 4 template-reuse packets, found {len(ring_fps)}"
    assert len(set(ring_fps)) == 1, (
        f"Ring packets should share one fingerprint but got {len(set(ring_fps))} distinct values: "
        f"{set(ring_fps)}"
    )
    assert clean_fps, "No clean packets with form16 found"
    ring_fp = ring_fps[0]
    for cfp in clean_fps:
        assert cfp != ring_fp, (
            "Ring fingerprint must differ from clean-packet fingerprints "
            "(ring uses 'QuickDocs Generator', clean uses 'TrustShield SynthGen 1.0')"
        )


def test_analyze_returns_required_fields(labels: dict, analyzer) -> None:
    """Result dict must contain all required keys."""
    first_pkt = next(iter(labels))
    pkt_dir = PACKETS_DIR / first_pkt
    for doc_rec in _docs_in(pkt_dir):
        doc_path = pkt_dir / doc_rec["filename"]
        if not doc_path.exists():
            continue
        result = analyzer(str(doc_path), doc_type=doc_rec.get("doc_type", "other"))
        for field in ("filename", "doc_type", "page_count", "template_fingerprint", "findings"):
            assert field in result, f"Missing field '{field}' in result"
        assert isinstance(result["findings"], list)
        assert isinstance(result["template_fingerprint"], str)
        assert len(result["template_fingerprint"]) > 0
        break


def test_each_finding_is_a_valid_evidence_item(labels: dict, analyzer) -> None:
    """Every finding dict must deserialize into a valid EvidenceItem with category=forensic."""
    from shared.schemas import EvidenceItem

    hit = False
    for pkt_id, entry in labels.items():
        if not _is_per_doc_forensic(entry.get("fraud_types", [])):
            continue
        pkt_dir = PACKETS_DIR / pkt_id
        for doc_rec in _docs_in(pkt_dir):
            doc_path = pkt_dir / doc_rec["filename"]
            if not doc_path.exists():
                continue
            result = analyzer(str(doc_path), doc_type=doc_rec.get("doc_type", "other"))
            for f in result["findings"]:
                ev = EvidenceItem.model_validate(f)
                assert ev.category.value == "forensic", f"Wrong category: {ev.category}"
                assert ev.description, "Empty description"
                assert ev.title, "Empty title"
                assert 0.0 <= ev.confidence <= 1.0
                hit = True
    assert hit, "No forensic findings found to validate — check that tamper packets exist"


# ---------------------------------------------------------------------------
# Signal-specific smoke tests
# ---------------------------------------------------------------------------

def test_whitebox_detection_on_forged_title(labels: dict, analyzer) -> None:
    for pkt_id, entry in labels.items():
        if "forged_title" in entry.get("fraud_types", []):
            pkt_dir = PACKETS_DIR / pkt_id
            doc_path = pkt_dir / "sale_deed.pdf"
            assert doc_path.exists(), f"sale_deed.pdf missing in {pkt_id}"
            result = analyzer(str(doc_path), doc_type="sale_deed", filename="sale_deed.pdf")
            titles = [f["title"] for f in result["findings"]]
            assert any("white" in t.lower() or "covered" in t.lower() or "edit" in t.lower()
                       for t in titles), (
                f"Expected whitebox finding on forged_title {pkt_id}, got: {titles}"
            )
            return
    pytest.fail("No forged_title packet found in labels.json")


def test_whitebox_detection_on_tampered_encumbrance(labels: dict, analyzer) -> None:
    for pkt_id, entry in labels.items():
        if "tampered_encumbrance" in entry.get("fraud_types", []):
            pkt_dir = PACKETS_DIR / pkt_id
            doc_path = pkt_dir / "encumbrance_certificate.pdf"
            assert doc_path.exists(), f"encumbrance_certificate.pdf missing in {pkt_id}"
            result = analyzer(str(doc_path), doc_type="encumbrance_certificate",
                              filename="encumbrance_certificate.pdf")
            titles = [f["title"] for f in result["findings"]]
            assert any("white" in t.lower() or "covered" in t.lower() or "edit" in t.lower()
                       for t in titles), (
                f"Expected whitebox finding on tampered_encumbrance {pkt_id}, got: {titles}"
            )
            return
    pytest.fail("No tampered_encumbrance packet found in labels.json")


def test_incremental_update_detection(labels: dict, analyzer) -> None:
    for pkt_id, entry in labels.items():
        if "incremental_update" in entry.get("fraud_types", []):
            pkt_dir = PACKETS_DIR / pkt_id
            doc_path = pkt_dir / "form16.pdf"
            assert doc_path.exists(), f"form16.pdf missing in {pkt_id}"
            result = analyzer(str(doc_path), doc_type="form16", filename="form16.pdf")
            titles = [f["title"] for f in result["findings"]]
            assert any("incremental" in t.lower() for t in titles), (
                f"Expected incremental-update finding on {pkt_id}, got: {titles}"
            )
            return
    pytest.fail("No incremental_update packet found")


def test_copy_paste_detection(labels: dict, analyzer) -> None:
    for pkt_id, entry in labels.items():
        if "copy_paste" in entry.get("fraud_types", []):
            pkt_dir = PACKETS_DIR / pkt_id
            doc_path = pkt_dir / "bank_statement.pdf"
            assert doc_path.exists(), f"bank_statement.pdf missing in {pkt_id}"
            result = analyzer(str(doc_path), doc_type="bank_statement",
                              filename="bank_statement.pdf")
            titles = [f["title"] for f in result["findings"]]
            assert any("duplicate" in t.lower() or "copy" in t.lower() for t in titles), (
                f"Expected copy-paste finding on {pkt_id}, got: {titles}"
            )
            return
    pytest.fail("No copy_paste packet found")


def test_font_inconsistency_detection(labels: dict, analyzer) -> None:
    for pkt_id, entry in labels.items():
        if "font_inconsistency" in entry.get("fraud_types", []):
            pkt_dir = PACKETS_DIR / pkt_id
            doc_path = pkt_dir / "form16.pdf"
            assert doc_path.exists(), f"form16.pdf missing in {pkt_id}"
            result = analyzer(str(doc_path), doc_type="form16", filename="form16.pdf")
            titles = [f["title"] for f in result["findings"]]
            assert any("font" in t.lower() for t in titles), (
                f"Expected font inconsistency finding on {pkt_id}, got: {titles}"
            )
            return
    pytest.fail("No font_inconsistency packet found")


def test_suspicious_metadata_detection(labels: dict, analyzer) -> None:
    for pkt_id, entry in labels.items():
        if "suspicious_metadata" in entry.get("fraud_types", []):
            pkt_dir = PACKETS_DIR / pkt_id
            doc_path = pkt_dir / "bank_statement.pdf"
            assert doc_path.exists(), f"bank_statement.pdf missing in {pkt_id}"
            result = analyzer(str(doc_path), doc_type="bank_statement",
                              filename="bank_statement.pdf")
            titles = [f["title"] for f in result["findings"]]
            assert titles, f"No findings on suspicious_metadata bank_statement in {pkt_id}"
            return
    pytest.fail("No suspicious_metadata packet found")


def test_future_date_detection(labels: dict, analyzer) -> None:
    """PKT with future creation date (timestamp_anomaly without behavioral_velocity) is caught."""
    for pkt_id, entry in labels.items():
        ft = set(entry.get("fraud_types", []))
        if ft == {"timestamp_anomaly"} and entry.get("label") == "fraud":
            pkt_dir = PACKETS_DIR / pkt_id
            # Check if any doc in this packet has a future date finding
            for doc_rec in _docs_in(pkt_dir):
                doc_path = pkt_dir / doc_rec["filename"]
                if not doc_path.exists():
                    continue
                result = analyzer(str(doc_path), doc_type=doc_rec.get("doc_type", "other"))
                if result["findings"]:
                    return  # found at least one finding on this timestamp_anomaly packet
            pytest.fail(
                f"timestamp_anomaly packet {pkt_id} raised no forensic findings on any document"
            )
    # If no pure timestamp_anomaly packet exists, skip (won't happen with current generator)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _docs_in(pkt_dir: Path) -> list[dict]:
    manifest_path = pkt_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    return json.loads(manifest_path.read_text()).get("documents", [])
